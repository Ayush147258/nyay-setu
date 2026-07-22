"""Evidence-grounded synthesis, adversarial critique, and mediation."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from app.document_intelligence.models import (
    AnalysisStatus,
    Citation,
    ClaimKind,
    DocumentIR,
    EvidenceAtom,
    EvidenceKind,
    IntegrityResult,
    LegalAnalysisReport,
    RelationshipEdge,
    ReportCaveat,
    ReportClaim,
    ReportSection,
    ResearchFinding,
    ReviewState,
    TimelineEvent,
)


WORKFLOW_VERSION = "track-c-1.1.0"
_MAX_REPORT_CLAIMS = 250


def _stable_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:24]


class SynthesisAgent:
    name = "synthesis_agent"
    version = "1.0.0"

    _SECTION_BY_KIND = {
        EvidenceKind.PERSON: ("parties", "Parties and Participants"),
        EvidenceKind.ORGANIZATION: ("parties", "Parties and Participants"),
        EvidenceKind.COURT: ("forum", "Courts and Authorities"),
        EvidenceKind.AUTHORITY: ("forum", "Courts and Authorities"),
        EvidenceKind.DATE: ("chronology", "Chronology"),
        EvidenceKind.LEGAL_PROVISION: ("law", "Statutes and Legal Provisions"),
        EvidenceKind.CASE_NUMBER: ("record", "Case and Document Record"),
        EvidenceKind.DOCUMENT_REFERENCE: ("record", "Case and Document Record"),
        EvidenceKind.MONEY: ("facts", "Material Facts"),
        EvidenceKind.CONTACT: ("facts", "Material Facts"),
        EvidenceKind.LOCATION: ("facts", "Material Facts"),
        EvidenceKind.STATEMENT: ("facts", "Material Facts"),
    }

    def synthesize(
        self,
        *,
        case_id: str,
        report_version: int,
        documents: list[DocumentIR],
        evidence: list[EvidenceAtom],
        relationships: list[RelationshipEdge],
        timeline: list[TimelineEvent],
        research_findings: list[ResearchFinding] | None = None,
        research_warnings: list[str] | None = None,
    ) -> LegalAnalysisReport:
        grouped: dict[tuple[str, str], list[ReportClaim]] = defaultdict(list)
        selected = evidence[:_MAX_REPORT_CLAIMS]
        for item in selected:
            section = self._SECTION_BY_KIND.get(item.kind, ("facts", "Material Facts"))
            claim_kind = ClaimKind.LAW if item.kind == EvidenceKind.LEGAL_PROVISION else ClaimKind.FACT
            grouped[section].append(
                ReportClaim(
                    claim_id=_stable_id("claim_", case_id, item.evidence_id),
                    statement=self._statement(item),
                    kind=claim_kind,
                    evidence_ids=[item.evidence_id],
                    confidence=item.confidence,
                    caveat="Human verification is required."
                    if item.review_state == ReviewState.NEEDS_REVIEW
                    else None,
                )
            )

        research_findings = research_findings or []
        for finding in research_findings:
            grouped[("research", "External Legal Research")].append(
                ReportClaim(
                    claim_id=_stable_id("claim_", case_id, finding.research_id),
                    statement=f"{finding.title}: {finding.excerpt}",
                    kind=ClaimKind.LAW,
                    research_ids=[finding.research_id],
                    confidence=0.75,
                    caveat="External authority must be checked in full before reliance.",
                )
            )

        sections = [
            ReportSection(section_id=section_id, title=title, claims=claims)
            for (section_id, title), claims in grouped.items()
        ]
        citations = [
            Citation(
                citation_id=_stable_id("cite_", item.evidence_id, item.source_spans[0].block_id),
                evidence_id=item.evidence_id,
                source_span=item.source_spans[0],
                display_label=self._citation_label(item, documents),
                source_type="uploaded_evidence",
            )
            for item in selected
        ]
        citations.extend(
            Citation(
                citation_id=_stable_id("cite_", finding.research_id),
                research_id=finding.research_id,
                source_url=finding.source_url,
                display_label=finding.citation or finding.title,
                source_type="external_authority",
            )
            for finding in research_findings
        )
        caveats: list[ReportCaveat] = []
        research_warnings = research_warnings or []
        if research_warnings:
            caveats.append(
                ReportCaveat(
                    caveat_id=_stable_id("caveat_", case_id, "research_warning"),
                    severity="warning",
                    title="External legal research incomplete",
                    detail=" ".join(research_warnings),
                )
            )
        if research_findings:
            caveats.append(
                ReportCaveat(
                    caveat_id=_stable_id("caveat_", case_id, "external_research"),
                    severity="info",
                    title="External authorities require full-text review",
                    detail="Research excerpts are leads, not substitutes for reading the cited judgment or statute in full.",
                )
            )
        if len(evidence) > _MAX_REPORT_CLAIMS:
            caveats.append(
                ReportCaveat(
                    caveat_id=_stable_id("caveat_", case_id, "claim_limit"),
                    severity="info",
                    title="Additional evidence available",
                    detail=(
                        f"The report summarizes {_MAX_REPORT_CLAIMS} of {len(evidence)} evidence atoms. "
                        "Search remains available across all sources."
                    ),
                )
            )
        for document in documents:
            if document.status.value != "ready":
                caveats.append(
                    ReportCaveat(
                        caveat_id=_stable_id("caveat_", document.version_id, document.status.value),
                        severity="blocking"
                        if document.status.value in {"ocr_required", "failed"}
                        else "warning",
                        title=f"Source requires review: {document.original_name}",
                        detail="; ".join(document.warnings)
                        or f"Parser status is {document.status.value}.",
                    )
                )
        if not evidence:
            caveats.append(
                ReportCaveat(
                    caveat_id=_stable_id("caveat_", case_id, "no_evidence"),
                    severity="blocking",
                    title="No verified evidence extracted",
                    detail=(
                        "The source documents produced no evidence atoms. Review parser output and OCR "
                        "before relying on this report."
                    ),
                )
            )
        return LegalAnalysisReport(
            report_id=_stable_id("report_", case_id, str(report_version), WORKFLOW_VERSION),
            case_id=case_id,
            version=report_version,
            title="Cited Legal Document Analysis",
            status=AnalysisStatus.VERIFYING,
            sections=sections,
            citations=citations,
            relationships=relationships,
            timeline=timeline,
            research_findings=research_findings,
            caveats=caveats,
            source_document_versions=[document.version_id for document in documents],
            workflow_version=WORKFLOW_VERSION,
        )

    @staticmethod
    def _statement(item: EvidenceAtom) -> str:
        if item.kind == EvidenceKind.PERSON:
            return f"The record identifies {item.value} as {item.label.lower()}."
        if item.kind in {EvidenceKind.COURT, EvidenceKind.AUTHORITY}:
            return f"The record refers to {item.value}."
        if item.kind == EvidenceKind.DATE:
            return f"The record contains the date {item.value}."
        if item.kind == EvidenceKind.LEGAL_PROVISION:
            return f"The source expressly refers to {item.value}."
        if item.kind == EvidenceKind.CASE_NUMBER:
            return f"The record identifies {item.value}."
        if item.kind == EvidenceKind.MONEY:
            return f"The source records the amount {item.value}."
        return f"The source contains the {item.label.lower()} value {item.value}."

    @staticmethod
    def _citation_label(item: EvidenceAtom, documents: list[DocumentIR]) -> str:
        span = item.source_spans[0]
        document = next(
            (candidate for candidate in documents if candidate.version_id == span.version_id),
            None,
        )
        name = document.original_name if document else "Source document"
        return f"{name}, page {span.page_number}"


class AdversarialCriticAgent:
    name = "adversarial_critic"
    version = "1.0.0"

    def critique(
        self,
        report: LegalAnalysisReport,
        evidence: list[EvidenceAtom],
        integrity: IntegrityResult,
    ) -> LegalAnalysisReport:
        caveats = {caveat.caveat_id: caveat for caveat in report.caveats}
        for item in evidence:
            if item.review_state == ReviewState.NEEDS_REVIEW:
                caveat = ReportCaveat(
                    caveat_id=_stable_id("caveat_", item.evidence_id, "low_confidence"),
                    severity="warning",
                    title="Extraction requires verification",
                    detail=(
                        f"{item.label}: {item.value} was extracted at "
                        f"{item.confidence:.0%} confidence."
                    ),
                    evidence_ids=[item.evidence_id],
                )
                caveats[caveat.caveat_id] = caveat

        conflict_kinds = {EvidenceKind.PERSON, EvidenceKind.CASE_NUMBER}
        groups: dict[tuple[EvidenceKind, str], list[EvidenceAtom]] = defaultdict(list)
        for item in evidence:
            if item.kind in conflict_kinds:
                groups[(item.kind, item.label.casefold())].append(item)
        for (kind, label), items in groups.items():
            values = {item.normalized_value for item in items}
            if len(values) > 1:
                caveat = ReportCaveat(
                    caveat_id=_stable_id("caveat_", report.case_id, kind.value, label, "conflict"),
                    severity="blocking",
                    title="Conflicting source values",
                    detail=(
                        f"The sources contain multiple values for {label}. "
                        "Human resolution is required."
                    ),
                    evidence_ids=[item.evidence_id for item in items],
                )
                caveats[caveat.caveat_id] = caveat

        for issue in integrity.issues:
            caveat = ReportCaveat(
                caveat_id=_stable_id("caveat_", issue.entity_id, issue.code),
                severity=issue.severity,
                title="Integrity verification issue",
                detail=issue.message,
            )
            caveats[caveat.caveat_id] = caveat
        return report.model_copy(update={"caveats": list(caveats.values())})


class VerifierMediatorAgent:
    name = "verifier_mediator"
    version = "1.0.0"

    def finalize(
        self,
        report: LegalAnalysisReport,
        integrity: IntegrityResult,
    ) -> LegalAnalysisReport:
        if integrity.valid:
            has_blocking = any(caveat.severity == "blocking" for caveat in report.caveats)
            status = AnalysisStatus.NEEDS_REVIEW if has_blocking else AnalysisStatus.COMPLETED
            return report.model_copy(update={"status": status})

        invalid_evidence: set[str] = set()
        invalid_claims: set[str] = set()
        invalid_citations: set[str] = set()
        for issue in integrity.issues:
            if issue.entity_type == "evidence":
                invalid_evidence.add(issue.entity_id)
            elif issue.entity_type == "claim":
                invalid_claims.add(issue.entity_id)
            elif issue.entity_type == "citation":
                invalid_citations.add(issue.entity_id)
        kept_citations = [
            citation
            for citation in report.citations
            if citation.citation_id not in invalid_citations
            and citation.evidence_id not in invalid_evidence
        ]
        kept_evidence = {citation.evidence_id for citation in kept_citations}
        kept_research = {
            citation.research_id for citation in kept_citations
            if citation.research_id
        }
        sections = [
            section.model_copy(
                update={
                    "claims": [
                        claim
                        for claim in section.claims
                        if claim.claim_id not in invalid_claims
                        and all(
                            evidence_id in kept_evidence
                            for evidence_id in claim.evidence_ids
                        )
                        and all(
                            research_id in kept_research
                            for research_id in claim.research_ids
                        )
                    ]
                }
            )
            for section in report.sections
        ]
        return report.model_copy(
            update={
                "sections": sections,
                "citations": kept_citations,
                "status": AnalysisStatus.NEEDS_REVIEW,
            }
        )

