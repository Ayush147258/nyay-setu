"""
app/agents/filing_agent.py

Filing Agent — assembles the final LegalDocument from all pipeline outputs.
Pure deterministic logic — no AI call.
"""

from __future__ import annotations

import logging

from app.models.case import ClassifiedCase, LegalContext
from app.models.document import (
    DebateRound,
    DocumentStatus,
    LegalDocument,
    UnresolvedGap,
    LegalPoint,
)
from app.core.document_builder import identify_gaps

logger = logging.getLogger(__name__)


def run_filing_agent(
    final_draft: str,
    classified: ClassifiedCase,
    legal_context: LegalContext,
    debate_rounds: list[DebateRound],
    unresolved_objections: list[str],
    mediator_override: bool,
    session_id: str = "",
    tier: str = "free",
    provider_used: str = "",
) -> LegalDocument:
    """
    Assembles the complete LegalDocument. No AI call.

    Combines:
    - Final patched draft from debate loop
    - Debate history (for AgentTraceLog on frontend)
    - Unresolved objections → UnresolvedGap list
    - Template gaps detected by document_builder.identify_gaps()
    - Filing instructions from legal_context
    - Status: HARDENED (no gaps) or ANNOTATED (gaps remain)
    """
    logger.info(
        "[filing] assembling document | case=%s rounds=%d unresolved=%d override=%s",
        classified.case_type,
        len(debate_rounds),
        len(unresolved_objections),
        mediator_override,
    )

    # Build UnresolvedGap list from two sources:
    # 1. Objections that the mediator could not resolve (need user input)
    # 2. Template placeholders still marked "[... — Please Fill]" in the final draft
    gap_from_objections = [
        UnresolvedGap(
            field=_slugify(obj),
            description=f"The document is missing: {obj}",
            how_to_fix=f"Please provide the following to complete your application: {obj}",
        )
        for obj in unresolved_objections
    ]
    gap_from_template = identify_gaps(final_draft)

    # Deduplicate by field slug
    seen_fields: set[str] = set()
    all_gaps: list[UnresolvedGap] = []
    for gap in gap_from_objections + gap_from_template:
        if gap.field not in seen_fields:
            seen_fields.add(gap.field)
            all_gaps.append(gap)

    # Status & confidence
    status = DocumentStatus.ANNOTATED if all_gaps else DocumentStatus.HARDENED
    confidence = 0.9 if not all_gaps else max(0.4, 0.9 - len(all_gaps) * 0.1)

    # Filing instructions (human-readable)
    portal = legal_context.filing_url or "your nearest district court / government office"
    docs_list = ", ".join(legal_context.required_documents) if legal_context.required_documents else "relevant identity and supporting documents"
    filing_instructions = (
        f"File this document at: {legal_context.authority_to_file}. "
        f"Portal / Office: {portal}. "
        f"Documents to attach: {docs_list}."
    )

    # Document title
    primary_section = (
        legal_context.applicable_sections[0]
        if legal_context.applicable_sections
        else ""
    )
    case_label = classified.case_type.value.replace("_", " ").title()
    document_title = (
        f"{primary_section} — {case_label} Application"
        if primary_section
        else f"{case_label} Application"
    )

    from app.models.case import UserTier
    doc = LegalDocument(
        case_type=classified.case_type,
        document_title=document_title,
        document_body=final_draft,
        debate_rounds=debate_rounds,
        total_rounds=len(debate_rounds),
        mediator_override_triggered=mediator_override,
        unresolved_gaps=all_gaps,
        applicable_sections=legal_context.applicable_sections,
        authority_to_file=legal_context.authority_to_file,
        filing_instructions=filing_instructions,
        required_documents=legal_context.required_documents,
        status=status,
        confidence_score=confidence,
        tier_used=UserTier(classified.tier.value),
        provider_used=provider_used,
        session_id=session_id,
    )

    logger.info(
        "[filing] document assembled | status=%s confidence=%.2f gaps=%d",
        status,
        confidence,
        len(all_gaps),
    )
    return doc


def _slugify(text: str) -> str:
    """Convert an objection string to a short snake_case field slug."""
    import re
    slug = re.sub(r"[^a-zA-Z0-9\s]", "", text.lower())
    slug = re.sub(r"\s+", "_", slug.strip())
    return slug[:50]
