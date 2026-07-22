"""Track C collaboration workflow with durable local artifacts."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from app.document_intelligence.extraction import LegalExtractorAgent
from app.document_intelligence.integrity import IntegrityVerifier
from app.document_intelligence.models import (
    AgentTraceEvent,
    AnalysisBundle,
    AnalysisRun,
    AnalysisStatus,
    DocumentIR,
    EvidenceAtom,
    IntegrityResult,
    LegalAnalysisReport,
    ResearchPacket,
    ReviewItem,
)
from app.document_intelligence.relationships import RelationshipAgent
from app.document_intelligence.research import (
    ControlledLegalResearchAgent,
    is_allowed_legal_source_url,
)
from app.document_intelligence.storage import DocumentStore
from app.document_intelligence.synthesis import (
    WORKFLOW_VERSION,
    AdversarialCriticAgent,
    SynthesisAgent,
    VerifierMediatorAgent,
)


T = TypeVar("T")
ProgressCallback = Callable[[AnalysisStatus, str, str], None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentAnalysisWorkflow:
    def __init__(self, store: DocumentStore):
        self.store = store
        self.extractor = LegalExtractorAgent()
        self.research_agent = ControlledLegalResearchAgent()
        self.relationship_agent = RelationshipAgent()
        self.synthesis_agent = SynthesisAgent()
        self.critic = AdversarialCriticAgent()
        self.verifier = IntegrityVerifier()
        self.mediator = VerifierMediatorAgent()

    def run(
        self,
        case_id: str,
        document_version_ids: list[str] | None = None,
        research_packet: ResearchPacket | None = None,
        enable_external_research: bool = False,
        progress_callback: ProgressCallback | None = None,
        tenant_id: str = "default",
    ) -> AnalysisBundle:
        documents = self._select_documents(
            case_id,
            document_version_ids,
            tenant_id=tenant_id,
        )
        if not documents:
            raise ValueError("No document versions are available for this case")
        run_id = str(uuid.uuid4())
        run = AnalysisRun(
            run_id=run_id,
            case_id=case_id,
            status=AnalysisStatus.EXTRACTING,
            workflow_version=WORKFLOW_VERSION,
            document_version_ids=[document.version_id for document in documents],
        )
        sequence = 0

        self._notify(
            progress_callback,
            AnalysisStatus.EXTRACTING,
            "Extractor",
            "Extracting source-linked facts and identifiers.",
        )
        evidence, event = self._timed_event(
            sequence,
            "Extractor",
            AnalysisStatus.EXTRACTING,
            "Extracted source-linked legal facts and identifiers.",
            lambda: self.extractor.extract(documents),
        )
        event.output_ids = [item.evidence_id for item in evidence]
        run.events.append(event)
        sequence += 1

        self._notify(
            progress_callback,
            AnalysisStatus.RETRIEVING,
            "Controlled Legal Research",
            (
                "Researching the allow-listed external legal source."
                if enable_external_research or research_packet is not None
                else "External legal research is disabled for this run."
            ),
        )
        active_research = research_packet or ResearchPacket(
            query="",
            status="disabled",
        )
        if enable_external_research or research_packet is not None:
            active_research, event = self._timed_event(
                sequence,
                "Controlled Legal Research",
                AnalysisStatus.RETRIEVING,
                "Queried the allow-listed external legal source.",
                lambda: self._research_safely(evidence, research_packet),
            )
            event.input_ids = [item.evidence_id for item in evidence]
            event.output_ids = [
                item.research_id for item in active_research.findings
            ]
            if active_research.status != "completed":
                event.summary = (
                    "External legal research did not complete; analysis continued with a warning."
                )
            run.events.append(event)
            sequence += 1

        self._notify(
            progress_callback,
            AnalysisStatus.RELATING,
            "Relationship",
            "Building source-backed relationships and chronology.",
        )
        related, event = self._timed_event(
            sequence,
            "Relationship",
            AnalysisStatus.RELATING,
            "Built party relationships and source-backed chronology.",
            lambda: self.relationship_agent.build(documents, evidence),
        )
        relationships, timeline = related
        event.input_ids = [item.evidence_id for item in evidence]
        event.output_ids = [
            *(item.relationship_id for item in relationships),
            *(item.event_id for item in timeline),
        ]
        run.events.append(event)
        sequence += 1

        report_version = self._next_report_version(case_id, tenant_id=tenant_id)
        self._notify(
            progress_callback,
            AnalysisStatus.SYNTHESIZING,
            "Synthesis",
            "Compiling the structured analysis report.",
        )
        report, event = self._timed_event(
            sequence,
            "Synthesis",
            AnalysisStatus.SYNTHESIZING,
            "Compiled a structured legal analysis from verified evidence.",
            lambda: self.synthesis_agent.synthesize(
                case_id=case_id,
                report_version=report_version,
                documents=documents,
                evidence=evidence,
                relationships=relationships,
                timeline=timeline,
                research_findings=active_research.findings,
                research_warnings=active_research.warnings,
            ),
        )
        event.input_ids = [item.evidence_id for item in evidence]
        event.output_ids = [report.report_id]
        run.events.append(event)
        sequence += 1

        self._notify(
            progress_callback,
            AnalysisStatus.CRITIQUING,
            "Adversarial",
            "Checking contradictions and unsupported claims.",
        )
        initial_integrity = self.verifier.verify(
            documents=documents,
            evidence=evidence,
            relationships=relationships,
            report=report,
        )
        critiqued, event = self._timed_event(
            sequence,
            "Adversarial",
            AnalysisStatus.CRITIQUING,
            "Checked contradictions, confidence gates, and unsupported claims.",
            lambda: self.critic.critique(report, evidence, initial_integrity),
        )
        event.input_ids = [report.report_id]
        event.output_ids = [caveat.caveat_id for caveat in critiqued.caveats]
        run.events.append(event)
        sequence += 1

        self._notify(
            progress_callback,
            AnalysisStatus.VERIFYING,
            "Verifier / Mediator",
            "Verifying provenance and resolving integrity findings.",
        )
        mediated = self.mediator.finalize(critiqued, initial_integrity)
        final_integrity = self.verifier.verify(
            documents=documents,
            evidence=evidence,
            relationships=mediated.relationships,
            report=mediated,
        )
        round_number = 1
        if not final_integrity.valid:
            round_number = 2
            mediated = self.mediator.finalize(mediated, final_integrity)
            final_integrity = self.verifier.verify(
                documents=documents,
                evidence=evidence,
                relationships=mediated.relationships,
                report=mediated,
            )
        verifier_event = AgentTraceEvent(
            sequence=sequence,
            agent="Verifier / Mediator",
            status=AnalysisStatus.VERIFYING,
            summary=(
                "Approved provenance and claim support."
                if final_integrity.valid
                else "Stopped automatic approval and exposed unresolved integrity defects."
            ),
            round_number=round_number,
            started_at=_now(),
            completed_at=_now(),
            input_ids=[mediated.report_id],
            output_ids=[issue.entity_id for issue in final_integrity.issues],
        )
        run.events.append(verifier_event)

        if not final_integrity.valid:
            mediated = mediated.model_copy(update={"status": AnalysisStatus.NEEDS_REVIEW})
        run.status = mediated.status
        run.report_id = mediated.report_id
        run.updated_at = _now()
        review_items = self._review_items(case_id, mediated, final_integrity)
        bundle = AnalysisBundle(
            run=run,
            report=mediated,
            evidence=evidence,
            research=active_research,
            integrity=final_integrity,
            review_items=review_items,
        )
        self.store.save_artifact(
            case_id,
            "runs",
            run_id,
            run.model_dump(mode="json"),
            tenant_id=tenant_id,
        )
        self.store.save_artifact(
            case_id,
            "reports",
            mediated.report_id,
            mediated.model_dump(mode="json"),
            tenant_id=tenant_id,
        )
        self.store.save_artifact(
            case_id,
            "research",
            run_id,
            active_research.model_dump(mode="json"),
            tenant_id=tenant_id,
        )
        self.store.save_artifact(
            case_id,
            "evidence",
            run_id,
            {"items": [item.model_dump(mode="json") for item in evidence]},
            tenant_id=tenant_id,
        )
        self.store.save_artifact(
            case_id,
            "integrity",
            run_id,
            {
                "result": final_integrity.model_dump(mode="json"),
                "review_items": [
                    item.model_dump(mode="json") for item in review_items
                ],
            },
            tenant_id=tenant_id,
        )
        return bundle

    @staticmethod
    def _notify(
        callback: ProgressCallback | None,
        status: AnalysisStatus,
        agent: str,
        message: str,
    ) -> None:
        if callback is not None:
            callback(status, agent, message)

    def _research_safely(
        self,
        evidence: list[EvidenceAtom],
        supplied: ResearchPacket | None,
    ) -> ResearchPacket:
        try:
            packet = supplied or asyncio.run(self.research_agent.research(evidence))
        except Exception as exc:
            query = " ".join(item.value for item in evidence[:8])[:500]
            return ResearchPacket(
                query=query,
                status="failed",
                warnings=[
                    f"External legal research failed safely: {type(exc).__name__}."
                ],
            )
        return self._sanitize_research_packet(packet)

    @staticmethod
    def _sanitize_research_packet(packet: ResearchPacket) -> ResearchPacket:
        findings = [
            finding
            for finding in packet.findings
            if is_allowed_legal_source_url(finding.source_url)
        ]
        skipped = len(packet.findings) - len(findings)
        warnings = list(packet.warnings)
        if skipped:
            warnings.append(
                f"{skipped} research result(s) were excluded because their source URL was invalid."
            )
        return packet.model_copy(
            update={"findings": findings, "warnings": warnings}
        )

    def _select_documents(
        self,
        case_id: str,
        version_ids: list[str] | None,
        *,
        tenant_id: str,
    ) -> list[DocumentIR]:
        documents = self.store.list_versions(
            case_id,
            tenant_id=tenant_id,
        )
        if version_ids is None:
            latest_by_document: dict[str, DocumentIR] = {}
            for document in documents:
                latest_by_document[document.document_id] = document
            return list(latest_by_document.values())
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
        return selected

    def _next_report_version(
        self,
        case_id: str,
        *,
        tenant_id: str,
    ) -> int:
        try:
            latest = LegalAnalysisReport.model_validate(
                self.store.latest_artifact(
                    case_id,
                    "reports",
                    tenant_id=tenant_id,
                )
            )
            return latest.version + 1
        except FileNotFoundError:
            return 1

    @staticmethod
    def _timed_event(
        sequence: int,
        agent: str,
        status: AnalysisStatus,
        summary: str,
        operation: Callable[[], T],
    ) -> tuple[T, AgentTraceEvent]:
        started = _now()
        result = operation()
        event = AgentTraceEvent(
            sequence=sequence,
            agent=agent,
            status=status,
            summary=summary,
            started_at=started,
            completed_at=_now(),
        )
        return result, event

    @staticmethod
    def _review_items(
        case_id: str,
        report: LegalAnalysisReport,
        integrity: IntegrityResult,
    ) -> list[ReviewItem]:
        items = [
            ReviewItem(
                review_id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{case_id}:caveat:{caveat.caveat_id}",
                    )
                ),
                case_id=case_id,
                source_type="report_caveat",
                source_id=caveat.caveat_id,
                severity=(
                    "blocking"
                    if caveat.severity == "blocking"
                    else "warning"
                ),
                reason=f"{caveat.title}: {caveat.detail}",
            )
            for caveat in report.caveats
            if caveat.severity in {"warning", "blocking"}
        ]
        items.extend(
            ReviewItem(
                review_id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{case_id}:integrity:{issue.code}:{issue.entity_id}",
                    )
                ),
                case_id=case_id,
                source_type=issue.entity_type,
                source_id=issue.entity_id,
                severity=issue.severity,
                reason=issue.message,
            )
            for issue in integrity.issues
        )
        return items

