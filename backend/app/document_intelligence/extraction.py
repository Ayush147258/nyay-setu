"""Deterministic legal evidence extraction with exact source spans."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass

from app.document_intelligence.models import (
    DocumentBlock,
    DocumentIR,
    EvidenceAtom,
    EvidenceKind,
    ParseStatus,
    ReviewState,
    SourceSpan,
)


EXTRACTOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class ExtractionRule:
    name: str
    kind: EvidenceKind
    pattern: re.Pattern[str]
    confidence: float
    value_group: str | int = 0


_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)

RULES = (
    ExtractionRule(
        "numeric_date",
        EvidenceKind.DATE,
        re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2}\b"),
        0.96,
    ),
    ExtractionRule(
        "named_date",
        EvidenceKind.DATE,
        re.compile(rf"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:{_MONTHS})\s+(?:19|20)\d{{2}}\b", re.I),
        0.94,
    ),
    ExtractionRule(
        "case_number",
        EvidenceKind.CASE_NUMBER,
        re.compile(
            r"\b(?:case|petition|appeal|writ|fir|complaint|suit|application|crl\.?|civil)\s*"
            r"(?:no\.?|number)?\s*[:#-]?\s*[A-Z0-9./-]{2,}\s+(?:of\s+)?(?:19|20)\d{2}\b",
            re.I,
        ),
        0.93,
    ),
    ExtractionRule(
        "legal_provision",
        EvidenceKind.LEGAL_PROVISION,
        re.compile(
            r"\b(?:section|article|rule|order)\s+\d+[A-Za-z]?(?:\([0-9A-Za-z]+\))*"
            r"(?:\s+(?:of|under)\s+the\s+[A-Za-z0-9 .,'()-]{3,80}?(?:Act|Code|Rules|Constitution)(?:,?\s*\d{4})?)?",
            re.I,
        ),
        0.92,
    ),
    ExtractionRule(
        "money",
        EvidenceKind.MONEY,
        re.compile(r"(?:Rs\.?|INR|₹)\s*[0-9][0-9,]*(?:\.\d{1,2})?", re.I),
        0.95,
    ),
    ExtractionRule(
        "email",
        EvidenceKind.CONTACT,
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        0.98,
    ),
    ExtractionRule(
        "phone",
        EvidenceKind.CONTACT,
        re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}(?!\d)"),
        0.92,
    ),
    ExtractionRule(
        "court",
        EvidenceKind.COURT,
        re.compile(
            r"\b(?:Supreme Court of India|[A-Z][A-Za-z ]+ High Court|District(?: and Sessions)? Court|"
            r"Court of (?:the )?[A-Za-z .]+|Judicial Magistrate(?: First Class)?|Tribunal)\b",
            re.I,
        ),
        0.88,
    ),
    ExtractionRule(
        "authority",
        EvidenceKind.AUTHORITY,
        re.compile(
            r"\b(?:Police Station|District Magistrate|Sub-Divisional Magistrate|Tehsildar|Collector|"
            r"Public Information Officer|Government of [A-Za-z ]+|Ministry of [A-Za-z &]+|Department of [A-Za-z &]+)\b",
            re.I,
        ),
        0.84,
    ),
    ExtractionRule(
        "document_reference",
        EvidenceKind.DOCUMENT_REFERENCE,
        re.compile(
            r"\b(?:affidavit|annexure|exhibit|charge[- ]sheet|judgment|order|notice|summons|warrant|"
            r"fir|complaint|petition|written statement|medical report|forensic report|sale deed|registry)"
            r"(?:\s+(?:no\.?|number|[A-Z]))?\s*[A-Z0-9./-]*",
            re.I,
        ),
        0.82,
    ),
)

_ROLE_PATTERN = re.compile(
    r"\b(?P<role>petitioner|applicant|complainant|informant|respondent|accused|appellant|"
    r"defendant|plaintiff|deponent|witness)\s*(?:no\.?\s*\d+)?\s*[:.-]\s*"
    r"(?P<name>[A-Z][A-Za-z.' -]{2,80})(?=\n|,|;|\s+(?:aged|age|son|daughter|wife|resident|address)\b|$)",
    re.I,
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,.;:-").casefold()


def _evidence_id(case_id: str, kind: EvidenceKind, label: str, normalized: str) -> str:
    raw = f"{case_id}:{kind.value}:{label.casefold()}:{normalized}".encode("utf-8")
    return "ev_" + hashlib.sha256(raw).hexdigest()[:24]


def _span(document: DocumentIR, block: DocumentBlock, start: int, end: int) -> SourceSpan:
    return SourceSpan(
        document_id=document.document_id,
        version_id=document.version_id,
        page_number=block.page_number,
        block_id=block.block_id,
        start_char=start,
        end_char=end,
        exact_quote=block.text[start:end],
        bbox=block.bbox,
    )


class LegalExtractorAgent:
    """Rule-first Extractor Agent.

    Rules provide predictable evidence for common legal identifiers. A future
    schema-constrained model extractor can add candidates, but those candidates
    must pass the same span validation before entering the evidence store.
    """

    name = "legal_extractor"
    version = EXTRACTOR_VERSION

    def extract(self, documents: list[DocumentIR]) -> list[EvidenceAtom]:
        candidates: dict[tuple[EvidenceKind, str, str], list[tuple[SourceSpan, float]]] = defaultdict(list)
        case_ids = {document.case_id for document in documents}
        if len(case_ids) > 1:
            raise ValueError("Extractor input must be isolated to one case")
        case_id = next(iter(case_ids), "")

        for document in documents:
            if document.status not in {ParseStatus.READY, ParseStatus.PARTIAL}:
                continue
            for page in document.pages:
                for block in page.blocks:
                    for match in _ROLE_PATTERN.finditer(block.text):
                        value = match.group("name").strip()
                        label = match.group("role").title()
                        candidates[(EvidenceKind.PERSON, label, _normalize(value))].append(
                            (_span(document, block, match.start("name"), match.end("name")), 0.90)
                        )
                    for rule in RULES:
                        for match in rule.pattern.finditer(block.text):
                            value = match.group(rule.value_group).strip(" ,.;:-")
                            if not value:
                                continue
                            label = rule.name.replace("_", " ").title()
                            candidates[(rule.kind, label, _normalize(value))].append(
                                (_span(document, block, match.start(rule.value_group), match.end(rule.value_group)), rule.confidence)
                            )

        evidence: list[EvidenceAtom] = []
        for (kind, label, normalized), occurrences in sorted(
            candidates.items(), key=lambda item: (item[0][0].value, item[0][1], item[0][2])
        ):
            spans: list[SourceSpan] = []
            seen_spans: set[tuple[str, str, int, int]] = set()
            for source_span, _ in occurrences:
                key = (
                    source_span.version_id,
                    source_span.block_id,
                    source_span.start_char,
                    source_span.end_char,
                )
                if key not in seen_spans:
                    spans.append(source_span)
                    seen_spans.add(key)
            confidence = min(
                max(rule_confidence * self._block_confidence(span, documents), 0.0)
                for span, rule_confidence in occurrences
            )
            evidence.append(
                EvidenceAtom(
                    evidence_id=_evidence_id(case_id, kind, label, normalized),
                    case_id=case_id,
                    kind=kind,
                    label=label,
                    value=occurrences[0][0].exact_quote,
                    normalized_value=normalized,
                    confidence=round(confidence, 4),
                    review_state=ReviewState.VERIFIED if confidence >= 0.75 else ReviewState.NEEDS_REVIEW,
                    source_spans=spans,
                    extractor_name=self.name,
                    extractor_version=self.version,
                )
            )
        return evidence

    @staticmethod
    def _block_confidence(span: SourceSpan, documents: list[DocumentIR]) -> float:
        for document in documents:
            if document.version_id != span.version_id:
                continue
            block = document.block_map().get(span.block_id)
            if block:
                return block.confidence
        return 0.0

