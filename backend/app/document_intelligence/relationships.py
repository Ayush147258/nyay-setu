"""Relationship and chronology derivation from verified evidence."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime

from app.document_intelligence.models import (
    DocumentIR,
    EvidenceAtom,
    EvidenceKind,
    RelationshipEdge,
    ReviewState,
    TimelineEvent,
)


_ACTOR_KINDS = {EvidenceKind.PERSON, EvidenceKind.ORGANIZATION, EvidenceKind.COURT, EvidenceKind.AUTHORITY}
_OPPOSING_ROLES = {
    frozenset({"petitioner", "respondent"}),
    frozenset({"applicant", "respondent"}),
    frozenset({"complainant", "accused"}),
    frozenset({"plaintiff", "defendant"}),
    frozenset({"appellant", "respondent"}),
}


def _stable_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:24]


def _normalize_date(value: str) -> str | None:
    formats = (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d %B %Y",
        "%d %b %Y",
    )
    for date_format in formats:
        try:
            return datetime.strptime(value.strip(), date_format).date().isoformat()
        except ValueError:
            continue
    return None


class RelationshipAgent:
    name = "relationship_agent"
    version = "1.0.0"

    def build(
        self, documents: list[DocumentIR], evidence: list[EvidenceAtom]
    ) -> tuple[list[RelationshipEdge], list[TimelineEvent]]:
        case_ids = {item.case_id for item in evidence}
        if len(case_ids) > 1:
            raise ValueError("Relationship input must be isolated to one case")
        case_id = next(iter(case_ids), documents[0].case_id if documents else "")
        by_block: dict[tuple[str, str], list[EvidenceAtom]] = defaultdict(list)
        for item in evidence:
            for span in item.source_spans:
                by_block[(span.version_id, span.block_id)].append(item)

        relationships: dict[str, RelationshipEdge] = {}
        for items in by_block.values():
            actors = [item for item in items if item.kind in _ACTOR_KINDS][:8]
            for index, source in enumerate(actors):
                for target in actors[index + 1 :]:
                    if source.evidence_id == target.evidence_id:
                        continue
                    role_pair = frozenset({source.label.casefold(), target.label.casefold()})
                    if role_pair in _OPPOSING_ROLES:
                        relationship_type = "opposes"
                    elif source.kind == EvidenceKind.COURT or target.kind == EvidenceKind.COURT:
                        relationship_type = "appears_before"
                    else:
                        relationship_type = "co_mentioned"
                    relationship_id = _stable_id(
                        "rel_", case_id, source.evidence_id, target.evidence_id, relationship_type
                    )
                    confidence = min(source.confidence, target.confidence)
                    relationships[relationship_id] = RelationshipEdge(
                        relationship_id=relationship_id,
                        case_id=case_id,
                        source_evidence_id=source.evidence_id,
                        target_evidence_id=target.evidence_id,
                        relationship_type=relationship_type,
                        description=f"{source.value} is {relationship_type.replace('_', ' ')} {target.value} in the source record.",
                        confidence=confidence,
                        supporting_evidence_ids=[source.evidence_id, target.evidence_id],
                        review_state=ReviewState.VERIFIED if confidence >= 0.75 else ReviewState.NEEDS_REVIEW,
                    )

        block_text = {
            (document.version_id, block.block_id): block.text
            for document in documents
            for page in document.pages
            for block in page.blocks
        }
        timeline: list[TimelineEvent] = []
        for date in (item for item in evidence if item.kind == EvidenceKind.DATE):
            first_span = date.source_spans[0]
            co_evidence = by_block[(first_span.version_id, first_span.block_id)]
            evidence_ids = list(dict.fromkeys([date.evidence_id, *(item.evidence_id for item in co_evidence)]))
            description = block_text.get((first_span.version_id, first_span.block_id), date.value).strip()
            if len(description) > 320:
                description = description[:317].rstrip() + "..."
            timeline.append(
                TimelineEvent(
                    event_id=_stable_id("evt_", case_id, date.evidence_id, description),
                    case_id=case_id,
                    date_text=date.value,
                    normalized_date=_normalize_date(date.value),
                    description=description,
                    evidence_ids=evidence_ids,
                    confidence=min(item.confidence for item in co_evidence),
                )
            )
        timeline.sort(key=lambda event: (event.normalized_date is None, event.normalized_date or event.date_text))
        return list(relationships.values()), timeline

