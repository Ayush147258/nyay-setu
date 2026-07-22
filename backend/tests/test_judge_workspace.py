from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.api.document_intelligence import _report_export_html
from app.document_intelligence.ingestion import DocumentIngestionService
from app.document_intelligence.models import ReportCaveat
from app.document_intelligence.storage import LocalDocumentStore
from app.document_intelligence.workflow import DocumentAnalysisWorkflow
from app.main import app


def test_judge_workspace_operational_routes_are_registered():
    paths = app.openapi()["paths"]
    required = {
        "/api/documents/upload",
        "/api/case-files/{case_id}/documents",
        "/api/case-files/{case_id}/analysis-jobs",
        "/api/analysis-jobs/{job_id}/events",
        "/api/case-files/{case_id}/workspace",
        "/api/case-files/{case_id}/reports",
        "/api/case-files/{case_id}/reports/{report_id}/export",
        "/api/case-files/{case_id}/reviews/{review_id}",
    }
    assert required <= set(paths)


def test_artifact_history_and_review_decisions_are_persisted(tmp_path):
    store = LocalDocumentStore(tmp_path)
    store.save_artifact("case-1", "reports", "report-1", {"version": 1})
    store.save_artifact("case-1", "reports", "report-2", {"version": 2})
    store.save_artifact(
        "case-1",
        "review-decisions",
        "review-1",
        {"review_id": "review-1", "status": "resolved"},
        immutable=False,
    )

    assert {item["version"] for item in store.list_artifacts("case-1", "reports")} == {1, 2}
    assert store.latest_artifact("case-1", "review-decisions")["status"] == "resolved"


def test_report_export_contains_caveats_and_workflow_provenance(tmp_path):
    store = LocalDocumentStore(tmp_path)
    result = DocumentIngestionService(store).ingest(
        case_id="case-export",
        filename="petition.txt",
        media_type="text/plain",
        stream=io.BytesIO(
            b"Petitioner: Ramesh Kumar\nFIR No. 12 of 2025 was filed on 01/04/2025."
        ),
    )
    report = DocumentAnalysisWorkflow(store).run(
        "case-export",
        [result.document.version_id],
    ).report
    report = report.model_copy(
        update={
            "caveats": [
                ReportCaveat(
                    caveat_id="caveat-1",
                    severity="blocking",
                    title="Missing annexure",
                    detail="The referenced annexure was not uploaded.",
                )
            ]
        }
    )

    rendered = _report_export_html(report)

    assert "Missing annexure" in rendered
    assert "was not uploaded" in rendered
    assert report.workflow_version in rendered
    assert "Verify cited source material" in rendered


def test_parallel_multi_file_ingestion_preserves_every_version(tmp_path):
    store = LocalDocumentStore(tmp_path, max_upload_bytes=2 * 1024 * 1024)
    service = DocumentIngestionService(store)

    def ingest(index: int):
        text = (
            f"Exhibit {index}\nFIR No. {1000 + index} of 2026\n"
            f"Filed on {index + 1:02d}/01/2026."
        )
        return service.ingest(
            case_id="case-load",
            filename=f"exhibit-{index}.txt",
            media_type="text/plain",
            stream=io.BytesIO(text.encode("utf-8")),
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(ingest, range(24)))

    versions = store.list_versions("case-load")
    assert len(versions) == 24
    assert len({item.document.sha256 for item in results}) == 24
    assert all(item.document.status.value == "ready" for item in results)


def test_parallel_pdf_table_extraction_is_deterministic(tmp_path):
    source = (
        Path(__file__).parent
        / "golden_corpus"
        / "generated"
        / "evidence-table-01.pdf"
    )
    payload = source.read_bytes()
    store = LocalDocumentStore(tmp_path / "table-load")

    def ingest(index: int):
        return DocumentIngestionService(store).ingest(
            case_id=f"case-table-{index}",
            filename=source.name,
            media_type="application/pdf",
            stream=io.BytesIO(payload),
        ).document

    with ThreadPoolExecutor(max_workers=8) as executor:
        documents = list(executor.map(ingest, range(16)))

    signatures = {
        tuple(
            (block.kind.value, block.text, block.confidence)
            for page in document.pages
            for block in page.blocks
        )
        for document in documents
    }
    assert len(signatures) == 1
    assert any(
        block.kind.value == "table"
        for page in documents[0].pages
        for block in page.blocks
    )
    assert not documents[0].warnings