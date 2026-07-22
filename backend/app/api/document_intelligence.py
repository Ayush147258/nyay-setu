"""Document intelligence APIs for case ingestion, analysis, search, and chat."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import uuid
from pathlib import Path
from time import monotonic

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.ai_router import call_with_fallback
from app.db.neon_client import get_pool
from app.document_intelligence.chat import CaseChatService
from app.document_intelligence.ingestion import DocumentIngestionService
from app.document_intelligence.models import (
    AnalysisRun,
    AnalyzeCaseRequest,
    CaseChatRequest,
    CaseChatResponse,
    DocumentIR,
    LegalAnalysisReport,
    SearchRequest,
    SearchResponse,
    UploadDocumentResponse,
)
from app.document_intelligence.jobs import (
    AnalysisJobRecord,
    AnalysisJobResponse,
    JobConflict,
    PostgresAnalysisJobRepository,
    TERMINAL_JOB_STATUSES,
    build_analysis_idempotency_key,
)
from app.document_intelligence.retrieval import CaseRetriever
from app.document_intelligence.security import (
    AuditEvent,
    DocumentPrincipal,
    PostgresDocumentSecurityRepository,
    UploadSignatureError,
    create_malware_scanner,
    require_document_principal,
    validate_upload_signature,
)
from app.document_intelligence.storage import (
    StorageError,
    UploadTooLarge,
    create_document_store,
)
from app.document_intelligence.synthesis import WORKFLOW_VERSION


logger = logging.getLogger(__name__)

router = APIRouter()
_store = create_document_store(settings)
_ingestion = DocumentIngestionService(_store)
_retriever = CaseRetriever()
_chat = CaseChatService(_retriever)
_malware_scanner = create_malware_scanner(settings)


def _latest_documents(case_id: str, tenant_id: str) -> list[DocumentIR]:
    latest: dict[str, DocumentIR] = {}
    for document in _store.list_versions(case_id, tenant_id=tenant_id):
        latest[document.document_id] = document
    return list(latest.values())


async def _document_answer_generator(system: str, prompt: str) -> str:
    answer, _ = await call_with_fallback(
        prompt=prompt,
        preferred="gemini",
        system=system,
        max_tokens=900,
    )
    return answer

def _configured_secret(value: str) -> bool:
    cleaned = (value or "").strip()
    lowered = cleaned.casefold()
    blocked_markers = ("your_", "placeholder", "changeme", "change_me", "dummy", "example", "not-set")
    return bool(cleaned) and not any(marker in lowered for marker in blocked_markers)


async def _job_repository() -> PostgresAnalysisJobRepository:
    if not settings.database_url:
        raise HTTPException(
            status_code=503,
            detail="Durable analysis jobs require DATABASE_URL.",
        )
    try:
        return PostgresAnalysisJobRepository(await get_pool())
    except Exception as exc:
        logger.exception("Unable to connect to the durable analysis queue")
        raise HTTPException(
            status_code=503,
            detail="The durable analysis queue is unavailable.",
        ) from exc


async def _security_repository() -> PostgresDocumentSecurityRepository:
    if not settings.database_url:
        raise HTTPException(
            status_code=503,
            detail="Document security requires DATABASE_URL.",
        )
    try:
        return PostgresDocumentSecurityRepository(await get_pool())
    except Exception as exc:
        logger.exception("Document security repository is unavailable")
        raise HTTPException(
            status_code=503,
            detail="Document authorization is temporarily unavailable.",
        ) from exc


def _case_uuid(case_id: str) -> uuid.UUID:
    try:
        resolved = uuid.UUID(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="case_id must be a UUID") from exc
    if case_id != str(resolved):
        raise HTTPException(
            status_code=400,
            detail="case_id must use canonical lowercase UUID form",
        )
    return resolved


async def _audit(
    repository: PostgresDocumentSecurityRepository,
    request: Request,
    principal: DocumentPrincipal,
    *,
    event_type: str,
    outcome: str,
    case_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        await repository.write_audit(
            AuditEvent(
                event_type=event_type,
                outcome=outcome,
                principal=principal,
                case_id=case_id,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=(request.headers.get("x-request-id") or "")[:128] or None,
                client_ip=request.client.host if request.client else None,
                user_agent=(request.headers.get("user-agent") or "")[:500] or None,
                metadata=metadata or {},
            )
        )
    except Exception as exc:
        logger.exception(
            "Document audit write failed | event=%s case=%s user=%s",
            event_type,
            case_id,
            principal.user_id,
        )
        if settings.document_audit_required and outcome == "allowed":
            raise HTTPException(
                status_code=503,
                detail="Access auditing is temporarily unavailable.",
            ) from exc


async def _authorize_case(
    case_id: str,
    principal: DocumentPrincipal,
    request: Request,
    *,
    bucket: str = "document_api",
    limit: int | None = None,
    window_seconds: int = 60,
) -> tuple[uuid.UUID, PostgresDocumentSecurityRepository]:
    resolved_case_id = _case_uuid(case_id)
    repository = await _security_repository()
    try:
        decision = await repository.consume_rate_limit(
            principal,
            bucket,
            limit=limit or settings.document_api_rate_limit_per_minute,
            window_seconds=window_seconds,
        )
    except Exception as exc:
        logger.exception(
            "Document rate-limit enforcement failed | bucket=%s user=%s",
            bucket,
            principal.user_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Document security enforcement is temporarily unavailable.",
        ) from exc
    if not decision.allowed:
        await _audit(
            repository,
            request,
            principal,
            event_type="document_rate_limited",
            outcome="denied",
            case_id=resolved_case_id,
            metadata={"bucket": bucket, "limit": decision.limit},
        )
        raise HTTPException(
            status_code=429,
            detail="Document API rate limit exceeded.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    try:
        owned = await repository.case_is_owned(resolved_case_id, principal)
    except Exception as exc:
        logger.exception(
            "Case ownership enforcement failed | case=%s user=%s",
            resolved_case_id,
            principal.user_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Document authorization is temporarily unavailable.",
        ) from exc
    if not owned:
        await _audit(
            repository,
            request,
            principal,
            event_type="case_access",
            outcome="denied",
            case_id=resolved_case_id,
        )
        raise HTTPException(status_code=404, detail="Case was not found.")
    return resolved_case_id, repository


def _select_analysis_documents(
    case_id: str,
    version_ids: list[str] | None,
    tenant_id: str,
) -> list[DocumentIR]:
    documents = _store.list_versions(case_id, tenant_id=tenant_id)
    if version_ids is None:
        latest: dict[str, DocumentIR] = {}
        for document in documents:
            latest[document.document_id] = document
        selected = list(latest.values())
    else:
        requested = set(version_ids)
        selected = [
            document
            for document in documents
            if document.version_id in requested
        ]
        found = {document.version_id for document in selected}
        missing = requested - found
        if missing:
            raise ValueError(
                f"Document versions do not belong to this case: {sorted(missing)}"
            )
    if not selected:
        raise FileNotFoundError("No document versions are available for this case")
    return selected


async def _enqueue_analysis(
    case_id: str,
    request: AnalyzeCaseRequest,
    principal: DocumentPrincipal,
) -> AnalysisJobResponse:
    case_uuid = _case_uuid(case_id)

    try:
        documents = await run_in_threadpool(
            _select_analysis_documents,
            case_id,
            request.document_version_ids,
            principal.tenant_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (StorageError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_versions = [
        (document.version_id, document.sha256)
        for document in documents
    ]
    idempotency_key = build_analysis_idempotency_key(
        case_id=case_id,
        tenant_id=principal.tenant_id,
        workflow_version=WORKFLOW_VERSION,
        document_versions=document_versions,
        enable_external_research=request.enable_external_research,
    )
    repository = await _job_repository()
    try:
        result = await repository.enqueue(
            case_id=case_uuid,
            tenant_id=principal.tenant_id,
            requested_by_user_id=principal.user_id,
            workflow_version=WORKFLOW_VERSION,
            idempotency_key=idempotency_key,
            document_version_ids=[
                document.version_id for document in documents
            ],
            document_hashes=[document.sha256 for document in documents],
            enable_external_research=request.enable_external_research,
            max_attempts=settings.analysis_job_max_attempts,
        )
    except Exception as exc:
        logger.exception("Unable to enqueue document analysis")
        raise HTTPException(
            status_code=503,
            detail="The analysis job could not be durably queued.",
        ) from exc
    return AnalysisJobResponse.from_record(
        result.job,
        deduplicated=not result.created,
    )

async def _authorized_job(
    job_id: uuid.UUID,
    principal: DocumentPrincipal,
    request: Request,
) -> tuple[
    AnalysisJobRecord,
    PostgresAnalysisJobRepository,
    uuid.UUID,
    PostgresDocumentSecurityRepository,
]:
    repository = await _job_repository()
    job = await repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job was not found")
    resolved_case_id, security = await _authorize_case(
        str(job.case_id),
        principal,
        request,
        bucket="document_job",
    )
    return job, repository, resolved_case_id, security


@router.post(
    "/documents/upload",
    response_model=UploadDocumentResponse,
    status_code=201,
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    case_id: str = Form(...),
    language_hint: str | None = Form(default=None),
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> UploadDocumentResponse:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
        bucket="document_upload",
        limit=settings.document_upload_rate_limit_per_minute,
    )
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required")

    reservation = None
    try:
        try:
            detected = await run_in_threadpool(
                validate_upload_signature,
                file.file,
                filename=file.filename,
                declared_media_type=file.content_type or "",
            )
        except UploadSignatureError as exc:
            await _audit(
                security,
                request,
                principal,
                event_type="document_upload",
                outcome="denied",
                case_id=resolved_case_id,
                resource_type="document",
                metadata={"reason": "invalid_signature"},
            )
            raise HTTPException(status_code=415, detail=str(exc)) from exc

        max_upload_bytes = settings.max_document_upload_mb * 1024 * 1024
        if detected.size_bytes > max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds the {settings.max_document_upload_mb} MB limit.",
            )
        reservation = await security.reserve_upload_quota(
            principal,
            resolved_case_id,
            size_bytes=detected.size_bytes,
            max_bytes=settings.document_monthly_upload_mb * 1024 * 1024,
            max_files=settings.document_monthly_upload_files,
        )
        if reservation is None:
            await _audit(
                security,
                request,
                principal,
                event_type="document_upload",
                outcome="denied",
                case_id=resolved_case_id,
                resource_type="document",
                metadata={"reason": "quota_exceeded"},
            )
            raise HTTPException(
                status_code=429,
                detail="Monthly document upload quota exceeded.",
            )

        scan = await run_in_threadpool(
            _malware_scanner.scan,
            file.file,
            filename=file.filename,
            media_type=detected.media_type,
        )
        if scan.status == "infected":
            await _audit(
                security,
                request,
                principal,
                event_type="document_upload",
                outcome="denied",
                case_id=resolved_case_id,
                resource_type="document",
                metadata={
                    "reason": "malware_detected",
                    "scanner": scan.scanner,
                    "signature": scan.signature or "unknown",
                },
            )
            raise HTTPException(
                status_code=422,
                detail="The uploaded file failed malware screening.",
            )
        if scan.status == "unavailable" or (
            scan.status == "skipped" and settings.document_malware_scan_required
        ):
            raise HTTPException(
                status_code=503,
                detail="Malware screening is temporarily unavailable.",
            )

        result = await run_in_threadpool(
            _ingestion.ingest,
            tenant_id=principal.tenant_id,
            case_id=case_id,
            filename=file.filename,
            media_type=detected.media_type,
            stream=file.file,
            language_hint=language_hint,
            security_metadata={
                "mime_signature_validated": True,
                "detected_document_kind": detected.document_kind,
                "malware_scan_status": scan.status,
                "malware_scanner": scan.scanner,
            },
        )
        if result.duplicate:
            await security.release_upload_quota(reservation.reservation_id)
        else:
            await security.commit_upload_quota(reservation.reservation_id)
        await _audit(
            security,
            request,
            principal,
            event_type="document_upload",
            outcome="allowed",
            case_id=resolved_case_id,
            resource_type="document",
            resource_id=result.document.version_id,
            metadata={
                "media_type": detected.media_type,
                "size_bytes": detected.size_bytes,
                "duplicate": result.duplicate,
                "scanner": scan.scanner,
                "scan_status": scan.status,
            },
        )
        return result
    except HTTPException:
        if reservation is not None:
            await security.release_upload_quota(reservation.reservation_id)
        raise
    except UploadTooLarge as exc:
        if reservation is not None:
            await security.release_upload_quota(reservation.reservation_id)
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except StorageError as exc:
        if reservation is not None:
            await security.release_upload_quota(reservation.reservation_id)
        await _audit(
            security,
            request,
            principal,
            event_type="document_upload",
            outcome="failed",
            case_id=resolved_case_id,
            resource_type="document",
            metadata={"error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()

@router.get(
    "/case-files/{case_id}/documents",
    response_model=list[DocumentIR],
)
async def list_case_documents(
    case_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> list[DocumentIR]:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    try:
        documents = await run_in_threadpool(
            _store.list_versions,
            case_id,
            tenant_id=principal.tenant_id,
        )
        await _audit(
            security,
            request,
            principal,
            event_type="document_list",
            outcome="allowed",
            case_id=resolved_case_id,
            resource_type="document",
            metadata={"version_count": len(documents)},
        )
        return documents
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/case-files/{case_id}/documents/{document_id}/versions/{version_id}",
    response_model=DocumentIR,
)
async def get_document_version(
    case_id: str,
    document_id: str,
    version_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> DocumentIR:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    try:
        document = await run_in_threadpool(
            _store.get_ir,
            case_id,
            document_id,
            version_id,
            tenant_id=principal.tenant_id,
        )
        await _audit(
            security,
            request,
            principal,
            event_type="document_read",
            outcome="allowed",
            case_id=resolved_case_id,
            resource_type="document_version",
            resource_id=version_id,
        )
        return document
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/case-files/{case_id}/documents/{document_id}/versions/{version_id}/download-url",
)
async def get_document_download_url(
    case_id: str,
    document_id: str,
    version_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> dict[str, str | int]:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    try:
        url = await run_in_threadpool(
            _store.create_download_url,
            case_id,
            document_id,
            version_id,
            tenant_id=principal.tenant_id,
            expires_seconds=settings.s3_signed_url_seconds,
        )
        await _audit(
            security,
            request,
            principal,
            event_type="document_download_url",
            outcome="allowed",
            case_id=resolved_case_id,
            resource_type="document_version",
            resource_id=version_id,
            metadata={"expires_seconds": settings.s3_signed_url_seconds},
        )
        return {
            "url": url,
            "expires_in": settings.s3_signed_url_seconds,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/case-files/{case_id}/analysis-jobs",
    response_model=list[AnalysisJobResponse],
)
async def list_case_analysis_jobs(
    case_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> list[AnalysisJobResponse]:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    repository = await _job_repository()
    jobs = await repository.list_case_jobs(
        resolved_case_id,
        tenant_id=principal.tenant_id,
    )
    await _audit(
        security,
        request,
        principal,
        event_type="analysis_job_list",
        outcome="allowed",
        case_id=resolved_case_id,
        resource_type="analysis_job",
        metadata={"job_count": len(jobs)},
    )
    return [AnalysisJobResponse.from_record(job) for job in jobs]


@router.get("/case-files/{case_id}/reports")
async def list_case_reports(
    case_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> list[LegalAnalysisReport]:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    payloads = await run_in_threadpool(
        _store.list_artifacts,
        case_id,
        "reports",
        tenant_id=principal.tenant_id,
    )
    reports = sorted(
        (LegalAnalysisReport.model_validate(payload) for payload in payloads),
        key=lambda report: report.version,
        reverse=True,
    )
    await _audit(
        security,
        request,
        principal,
        event_type="report_list",
        outcome="allowed",
        case_id=resolved_case_id,
        resource_type="report",
        metadata={"report_count": len(reports)},
    )
    return reports


@router.get(
    "/case-files/{case_id}/reports/{report_id}",
    response_model=LegalAnalysisReport,
)
async def get_case_report(
    case_id: str,
    report_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> LegalAnalysisReport:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    try:
        payload = await run_in_threadpool(
            _store.get_artifact,
            case_id,
            "reports",
            report_id,
            tenant_id=principal.tenant_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report was not found") from exc
    report = LegalAnalysisReport.model_validate(payload)
    await _audit(
        security,
        request,
        principal,
        event_type="report_read",
        outcome="allowed",
        case_id=resolved_case_id,
        resource_type="report",
        resource_id=report_id,
    )
    return report


def _report_export_html(report: LegalAnalysisReport) -> str:
    sections = []
    for section in report.sections:
        claims = "".join(
            "<li><strong>"
            + html.escape(claim.kind.value.title())
            + ":</strong> "
            + html.escape(claim.statement)
            + (f" <small>Confidence {claim.confidence:.0%}</small>" if claim.confidence else "")
            + "</li>"
            for claim in section.claims
        )
        sections.append(f"<section><h2>{html.escape(section.title)}</h2><ul>{claims}</ul></section>")
    caveats = "".join(
        f"<li class='{html.escape(item.severity)}'><strong>{html.escape(item.title)}</strong>: {html.escape(item.detail)}</li>"
        for item in report.caveats
    ) or "<li>No unresolved caveats.</li>"
    research = "".join(
        f"<li><strong>{html.escape(item.title)}</strong><br>{html.escape(item.citation or item.source_url)}</li>"
        for item in report.research_findings
    ) or "<li>No external legal research was requested.</li>"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
@page {{ size: A4; margin: 22mm 18mm; }}
body {{ font-family: sans-serif; color: #1b2a38; font-size: 11pt; line-height: 1.55; }}
h1 {{ font-size: 22pt; margin: 0 0 4pt; }}
h2 {{ font-size: 14pt; border-bottom: 1px solid #e2dac8; padding-bottom: 4pt; margin-top: 18pt; }}
.meta {{ color: #6b6457; margin-bottom: 18pt; }} li {{ margin: 5pt 0; }}
.warning, .blocking {{ color: #9d2f25; }} small {{ color: #6b6457; }}
footer {{ margin-top: 24pt; border-top: 1px solid #e2dac8; padding-top: 8pt; color: #6b6457; font-size: 9pt; }}
</style></head><body>
<h1>{html.escape(report.title)}</h1>
<div class='meta'>Case {html.escape(report.case_id)} | Report version {report.version} | {html.escape(report.created_at.isoformat())}</div>
{''.join(sections)}
<section><h2>External legal research</h2><ul>{research}</ul></section>
<section><h2>Unresolved caveats</h2><ul>{caveats}</ul></section>
<footer>Generated by NyaySetu workflow {html.escape(report.workflow_version)}. Verify cited source material before judicial reliance.</footer>
</body></html>"""


@router.get("/case-files/{case_id}/reports/{report_id}/export")
async def export_case_report(
    case_id: str,
    report_id: str,
    request: Request,
    format: str = "pdf",
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> Response:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    try:
        payload = await run_in_threadpool(
            _store.get_artifact,
            case_id,
            "reports",
            report_id,
            tenant_id=principal.tenant_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report was not found") from exc
    report = LegalAnalysisReport.model_validate(payload)
    selected_format = format.casefold()
    if selected_format == "json":
        content = json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        media_type = "application/json"
    elif selected_format == "pdf":
        try:
            from weasyprint import HTML
            content = await run_in_threadpool(
                lambda: HTML(string=_report_export_html(report)).write_pdf()
            )
        except Exception as exc:
            logger.exception("Report PDF generation failed | report=%s", report_id)
            raise HTTPException(
                status_code=503,
                detail="PDF export is temporarily unavailable.",
            ) from exc
        media_type = "application/pdf"
    else:
        raise HTTPException(status_code=400, detail="format must be pdf or json")
    await _audit(
        security,
        request,
        principal,
        event_type="report_export",
        outcome="allowed",
        case_id=resolved_case_id,
        resource_type="report",
        resource_id=report_id,
        metadata={"format": selected_format},
    )
    filename = f"nyaysetu-report-v{report.version}.{selected_format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/case-files/{case_id}/reviews/{review_id}")
async def update_review_item(
    case_id: str,
    review_id: str,
    payload: dict[str, str],
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> dict[str, str]:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    status = str(payload.get("status", "")).casefold()
    if status not in {"open", "resolved", "dismissed"}:
        raise HTTPException(
            status_code=422,
            detail="Review status must be open, resolved, or dismissed.",
        )
    decision = {
        "review_id": review_id,
        "status": status,
        "note": str(payload.get("note", ""))[:2000],
        "decided_by": str(principal.user_id),
    }
    await run_in_threadpool(
        _store.save_artifact,
        case_id,
        "review-decisions",
        review_id,
        decision,
        tenant_id=principal.tenant_id,
        immutable=False,
    )
    await _audit(
        security,
        request,
        principal,
        event_type="review_decision",
        outcome="allowed",
        case_id=resolved_case_id,
        resource_type="review_item",
        resource_id=review_id,
        metadata={"status": status},
    )
    return decision


@router.get("/case-files/{case_id}/workspace")
async def get_case_workspace(
    case_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> dict[str, object]:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    documents = await run_in_threadpool(
        _store.list_versions,
        case_id,
        tenant_id=principal.tenant_id,
    )
    reports_payload = await run_in_threadpool(
        _store.list_artifacts,
        case_id,
        "reports",
        tenant_id=principal.tenant_id,
    )
    reports = sorted(
        (LegalAnalysisReport.model_validate(payload) for payload in reports_payload),
        key=lambda item: item.version,
        reverse=True,
    )

    async def optional_latest(category: str):
        try:
            return await run_in_threadpool(
                _store.latest_artifact,
                case_id,
                category,
                tenant_id=principal.tenant_id,
            )
        except FileNotFoundError:
            return None

    repository = await _job_repository()
    jobs = await repository.list_case_jobs(
        resolved_case_id,
        tenant_id=principal.tenant_id,
    )
    run, evidence, integrity, research, decisions = await asyncio.gather(
        optional_latest("runs"),
        optional_latest("evidence"),
        optional_latest("integrity"),
        optional_latest("research"),
        run_in_threadpool(
            _store.list_artifacts,
            case_id,
            "review-decisions",
            tenant_id=principal.tenant_id,
        ),
    )
    await _audit(
        security,
        request,
        principal,
        event_type="workspace_read",
        outcome="allowed",
        case_id=resolved_case_id,
        resource_type="case_workspace",
        metadata={"documents": len(documents), "reports": len(reports)},
    )
    return {
        "documents": [item.model_dump(mode="json") for item in documents],
        "jobs": [AnalysisJobResponse.from_record(job).model_dump(mode="json") for job in jobs],
        "reports": [item.model_dump(mode="json") for item in reports],
        "latest_report": reports[0].model_dump(mode="json") if reports else None,
        "latest_run": run,
        "evidence": (evidence or {}).get("items", []),
        "integrity": (integrity or {}).get("result"),
        "review_items": (integrity or {}).get("review_items", []),
        "review_decisions": decisions,
        "research": research,
    }


@router.post(
    "/case-files/{case_id}/analysis-jobs",
    response_model=AnalysisJobResponse,
    status_code=202,
)
async def enqueue_analysis_job(
    case_id: str,
    request_body: AnalyzeCaseRequest,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> AnalysisJobResponse:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
        bucket="document_analysis",
        limit=settings.document_analysis_rate_limit_per_hour,
        window_seconds=3600,
    )
    result = await _enqueue_analysis(case_id, request_body, principal)
    await _audit(
        security,
        request,
        principal,
        event_type="analysis_job_enqueue",
        outcome="allowed",
        case_id=resolved_case_id,
        resource_type="analysis_job",
        resource_id=str(result.job_id),
        metadata={"deduplicated": result.deduplicated},
    )
    return result


@router.post(
    "/case-files/{case_id}/analyze",
    response_model=AnalysisJobResponse,
    status_code=202,
    deprecated=True,
)
async def enqueue_analysis_job_compatibility_alias(
    case_id: str,
    request_body: AnalyzeCaseRequest,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> AnalysisJobResponse:
    """Compatibility alias; analysis is always executed by the durable worker."""
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
        bucket="document_analysis",
        limit=settings.document_analysis_rate_limit_per_hour,
        window_seconds=3600,
    )
    result = await _enqueue_analysis(case_id, request_body, principal)
    await _audit(
        security,
        request,
        principal,
        event_type="analysis_job_enqueue",
        outcome="allowed",
        case_id=resolved_case_id,
        resource_type="analysis_job",
        resource_id=str(result.job_id),
        metadata={"compatibility_alias": True, "deduplicated": result.deduplicated},
    )
    return result

@router.get(
    "/analysis-jobs/{job_id}",
    response_model=AnalysisJobResponse,
)
async def get_analysis_job(
    job_id: uuid.UUID,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> AnalysisJobResponse:
    job, _, case_id, security = await _authorized_job(
        job_id,
        principal,
        request,
    )
    await _audit(
        security,
        request,
        principal,
        event_type="analysis_job_read",
        outcome="allowed",
        case_id=case_id,
        resource_type="analysis_job",
        resource_id=str(job_id),
        metadata={"status": job.status.value},
    )
    return AnalysisJobResponse.from_record(job)


@router.post(
    "/analysis-jobs/{job_id}/cancel",
    response_model=AnalysisJobResponse,
)
async def cancel_analysis_job(
    job_id: uuid.UUID,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> AnalysisJobResponse:
    _, repository, case_id, security = await _authorized_job(
        job_id,
        principal,
        request,
    )
    job = await repository.request_cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job was not found")
    await _audit(
        security,
        request,
        principal,
        event_type="analysis_job_cancel",
        outcome="allowed",
        case_id=case_id,
        resource_type="analysis_job",
        resource_id=str(job_id),
        metadata={"status": job.status.value},
    )
    return AnalysisJobResponse.from_record(job)


@router.post(
    "/analysis-jobs/{job_id}/retry",
    response_model=AnalysisJobResponse,
)
async def retry_analysis_job(
    job_id: uuid.UUID,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> AnalysisJobResponse:
    _, repository, case_id, security = await _authorized_job(
        job_id,
        principal,
        request,
    )
    try:
        job = await repository.retry(job_id)
    except JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job was not found")
    await _audit(
        security,
        request,
        principal,
        event_type="analysis_job_retry",
        outcome="allowed",
        case_id=case_id,
        resource_type="analysis_job",
        resource_id=str(job_id),
        metadata={"status": job.status.value},
    )
    return AnalysisJobResponse.from_record(job)


@router.get("/analysis-jobs/{job_id}/events")
async def stream_analysis_job_events(
    job_id: uuid.UUID,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> StreamingResponse:
    job, repository, case_id, security = await _authorized_job(
        job_id,
        principal,
        request,
    )
    await _audit(
        security,
        request,
        principal,
        event_type="analysis_job_events",
        outcome="allowed",
        case_id=case_id,
        resource_type="analysis_job",
        resource_id=str(job_id),
        metadata={"status": job.status.value},
    )

    try:
        after_sequence = int(request.headers.get("last-event-id", "-1"))
    except ValueError:
        after_sequence = -1

    async def event_stream():
        nonlocal after_sequence
        last_emit = monotonic()
        while True:
            if await request.is_disconnected():
                return
            try:
                events = await repository.list_events(
                    job_id,
                    after_sequence=after_sequence,
                )
                for event in events:
                    after_sequence = event.sequence
                    payload = json.dumps(
                        event.model_dump(mode="json"),
                        ensure_ascii=True,
                        separators=(",", ":"),
                    )
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {payload}\n\n"
                    )
                    last_emit = monotonic()

                current = await repository.get(job_id)
                if current is None:
                    payload = json.dumps(
                        {"message": "Analysis job was deleted."},
                        separators=(",", ":"),
                    )
                    yield f"event: error\ndata: {payload}\n\n"
                    return
                if current.status in TERMINAL_JOB_STATUSES and not events:
                    return

                if monotonic() - last_emit >= settings.analysis_sse_heartbeat_seconds:
                    yield ": heartbeat\n\n"
                    last_emit = monotonic()
                await asyncio.sleep(settings.analysis_sse_poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "Analysis job SSE stream failed | job=%s",
                    job_id,
                )
                payload = json.dumps(
                    {
                        "message": "The analysis event stream was interrupted.",
                        "error_type": type(exc).__name__,
                    },
                    separators=(",", ":"),
                )
                yield f"event: error\ndata: {payload}\n\n"
                return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get(
    "/case-files/{case_id}/analysis/latest",
    response_model=LegalAnalysisReport,
)
async def latest_case_analysis(
    case_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> LegalAnalysisReport:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    try:
        payload = await run_in_threadpool(
            _store.latest_artifact,
            case_id,
            "reports",
            tenant_id=principal.tenant_id,
        )
        report = LegalAnalysisReport.model_validate(payload)
        await _audit(
            security,
            request,
            principal,
            event_type="report_read",
            outcome="allowed",
            case_id=resolved_case_id,
            resource_type="report",
            resource_id=report.report_id,
        )
        return report
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="No analysis report exists for this case",
        ) from exc
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/case-files/{case_id}/analysis-runs/{run_id}",
    response_model=AnalysisRun,
)
async def get_analysis_run(
    case_id: str,
    run_id: str,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> AnalysisRun:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
    )
    try:
        payload = await run_in_threadpool(
            _store.get_artifact,
            case_id,
            "runs",
            run_id,
            tenant_id=principal.tenant_id,
        )
        run = AnalysisRun.model_validate(payload)
        await _audit(
            security,
            request,
            principal,
            event_type="analysis_run_read",
            outcome="allowed",
            case_id=resolved_case_id,
            resource_type="analysis_run",
            resource_id=run_id,
        )
        return run
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/case-files/{case_id}/search",
    response_model=SearchResponse,
)
async def search_case_documents(
    case_id: str,
    request_body: SearchRequest,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> SearchResponse:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
        bucket="document_search",
        limit=settings.document_search_rate_limit_per_minute,
    )
    try:
        documents = await run_in_threadpool(
            _latest_documents,
            case_id,
            principal.tenant_id,
        )
        hits = await run_in_threadpool(
            _retriever.search,
            documents,
            request_body.query,
            request_body.limit,
        )
        response = SearchResponse(hits=hits)
        await _audit(
            security,
            request,
            principal,
            event_type="document_search",
            outcome="allowed",
            case_id=resolved_case_id,
            resource_type="document",
            metadata={"hit_count": len(hits), "limit": request_body.limit},
        )
        return response
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/case-files/{case_id}/chat",
    response_model=CaseChatResponse,
)
async def chat_about_case(
    case_id: str,
    request_body: CaseChatRequest,
    request: Request,
    principal: DocumentPrincipal = Depends(require_document_principal),
) -> CaseChatResponse:
    resolved_case_id, security = await _authorize_case(
        case_id,
        principal,
        request,
        bucket="document_chat",
        limit=settings.document_search_rate_limit_per_minute,
    )
    try:
        documents = await run_in_threadpool(
            _latest_documents,
            case_id,
            principal.tenant_id,
        )
        if not documents:
            raise HTTPException(
                status_code=404,
                detail="Upload at least one document before using case chat",
            )
        if request_body.document_version_ids:
            requested_versions = set(request_body.document_version_ids)
            documents = [
                document
                for document in documents
                if document.version_id in requested_versions
            ]
            if not documents:
                raise HTTPException(
                    status_code=404,
                    detail="No uploaded document matched the selected @ document scope.",
                )
        has_provider = any(
            _configured_secret(value)
            for value in (
                settings.gemini_api_key,
                settings.anthropic_api_key,
                settings.groq_api_key,
            )
        )
        generator = (
            _document_answer_generator
            if settings.enable_document_ai_chat and has_provider
            else None
        )
        response = await _chat.answer(
            documents=documents,
            request=request_body,
            generator=generator,
        )
        await _audit(
            security,
            request,
            principal,
            event_type="document_chat",
            outcome="allowed",
            case_id=resolved_case_id,
            resource_type="document",
            metadata={"citation_count": len(response.citations), "document_scope_count": len(documents)},
        )
        return response
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


