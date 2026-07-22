"""Mechanical provenance and report-integrity verification."""

from __future__ import annotations

from app.document_intelligence.models import (
    ClaimKind,
    DocumentIR,
    EvidenceAtom,
    IntegrityIssue,
    IntegrityResult,
    LegalAnalysisReport,
    RelationshipEdge,
    ReviewState,
    SourceSpan,
)
from app.document_intelligence.research import is_allowed_legal_source_url


class IntegrityVerifier:
    def verify(
        self,
        *,
        documents: list[DocumentIR],
        evidence: list[EvidenceAtom],
        relationships: list[RelationshipEdge] | None = None,
        report: LegalAnalysisReport | None = None,
    ) -> IntegrityResult:
        issues: list[IntegrityIssue] = []
        document_map = {(document.document_id, document.version_id): document for document in documents}
        evidence_map = {item.evidence_id: item for item in evidence}
        checked_spans = 0

        for item in evidence:
            if item.case_id not in {document.case_id for document in documents}:
                issues.append(
                    self._issue("case_boundary", "blocking", "Evidence belongs to a different case", "evidence", item.evidence_id)
                )
            for span in item.source_spans:
                checked_spans += 1
                span_issue = self._verify_span(span, document_map)
                if span_issue:
                    issues.append(
                        self._issue(span_issue[0], "blocking", span_issue[1], "evidence", item.evidence_id)
                    )
            if item.confidence < 0.75 and item.review_state == ReviewState.VERIFIED:
                issues.append(
                    self._issue(
                        "confidence_gate",
                        "blocking",
                        "Low-confidence evidence was promoted without review",
                        "evidence",
                        item.evidence_id,
                    )
                )

        for relationship in relationships or []:
            missing = [
                evidence_id
                for evidence_id in relationship.supporting_evidence_ids
                if evidence_id not in evidence_map
            ]
            if missing:
                issues.append(
                    self._issue(
                        "relationship_support",
                        "blocking",
                        f"Relationship references missing evidence: {missing}",
                        "relationship",
                        relationship.relationship_id,
                    )
                )

        checked_claims = 0
        if report:
            citation_evidence = {
                citation.evidence_id for citation in report.citations
                if citation.evidence_id
            }
            citation_research = {
                citation.research_id for citation in report.citations
                if citation.research_id
            }
            research_map = {item.research_id: item for item in report.research_findings}
            for finding in report.research_findings:
                if not is_allowed_legal_source_url(finding.source_url):
                    issues.append(
                        self._issue(
                            "research_source",
                            "blocking",
                            "Research finding is outside the legal-source allow-list",
                            "research",
                            finding.research_id,
                        )
                    )
                if finding.research_id not in citation_research:
                    issues.append(
                        self._issue(
                            "research_citation",
                            "blocking",
                            "Research finding has no report citation",
                            "research",
                            finding.research_id,
                        )
                    )
            for citation in report.citations:
                if citation.evidence_id:
                    if citation.evidence_id not in evidence_map:
                        issues.append(
                            self._issue(
                                "citation_evidence",
                                "blocking",
                                "Citation does not resolve to a stored evidence atom",
                                "citation",
                                citation.citation_id,
                            )
                        )
                        continue
                    span_issue = self._verify_span(citation.source_span, document_map)
                    if span_issue:
                        issues.append(
                            self._issue(
                                span_issue[0], "blocking", span_issue[1], "citation", citation.citation_id
                            )
                        )
                    continue
                finding = research_map.get(citation.research_id or "")
                if (
                    not finding
                    or finding.source_url != citation.source_url
                    or not is_allowed_legal_source_url(citation.source_url or "")
                ):
                    issues.append(
                        self._issue(
                            "citation_research",
                            "blocking",
                            "External citation is missing, changed, or outside the legal-source allow-list",
                            "citation",
                            citation.citation_id,
                        )
                    )
            for section in report.sections:
                for claim in section.claims:
                    checked_claims += 1
                    unsupported = (
                        claim.kind == ClaimKind.FACT and not claim.evidence_ids
                    ) or (
                        claim.kind == ClaimKind.LAW
                        and not claim.evidence_ids
                        and not claim.research_ids
                    )
                    if unsupported:
                        issues.append(
                            self._issue(
                                "unsupported_claim",
                                "blocking",
                                "A factual or legal claim has no source support",
                                "claim",
                                claim.claim_id,
                            )
                        )
                    missing = [item for item in claim.evidence_ids if item not in evidence_map]
                    if missing:
                        issues.append(
                            self._issue(
                                "claim_evidence",
                                "blocking",
                                f"Claim references missing evidence: {missing}",
                                "claim",
                                claim.claim_id,
                            )
                        )
                    missing_research = [
                        item for item in claim.research_ids
                        if item not in research_map
                    ]
                    if missing_research:
                        issues.append(
                            self._issue(
                                "claim_research",
                                "blocking",
                                f"Claim references missing research: {missing_research}",
                                "claim",
                                claim.claim_id,
                            )
                        )
                    uncited = [item for item in claim.evidence_ids if item not in citation_evidence]
                    if uncited:
                        issues.append(
                            self._issue(
                                "claim_citation",
                                "blocking",
                                f"Claim evidence has no report citation: {uncited}",
                                "claim",
                                claim.claim_id,
                            )
                        )
                    uncited_research = [
                        item for item in claim.research_ids
                        if item not in citation_research
                    ]
                    if uncited_research:
                        issues.append(
                            self._issue(
                                "claim_research_citation",
                                "blocking",
                                f"Claim research has no report citation: {uncited_research}",
                                "claim",
                                claim.claim_id,
                            )
                        )

        return IntegrityResult(
            valid=not any(issue.severity == "blocking" for issue in issues),
            issues=issues,
            checked_claims=checked_claims,
            checked_evidence=len(evidence),
            checked_spans=checked_spans,
        )

    @staticmethod
    def _verify_span(
        span: SourceSpan, document_map: dict[tuple[str, str], DocumentIR]
    ) -> tuple[str, str] | None:
        document = document_map.get((span.document_id, span.version_id))
        if not document:
            return "source_version", "Source document version does not exist"
        block = document.block_map().get(span.block_id)
        if not block or block.page_number != span.page_number:
            return "source_block", "Source page or block does not exist"
        if span.end_char > len(block.text):
            return "source_bounds", "Source character range exceeds the stored block"
        if block.text[span.start_char : span.end_char] != span.exact_quote:
            return "source_quote", "Source quote does not match the immutable block text"
        return None

    @staticmethod
    def _issue(code: str, severity: str, message: str, entity_type: str, entity_id: str) -> IntegrityIssue:
        return IntegrityIssue(
            code=code,
            severity=severity,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
        )

