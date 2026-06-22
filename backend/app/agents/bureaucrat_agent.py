"""
app/agents/bureaucrat_agent.py

Bureaucrat Agent — adversarially attacks the advocate's draft.
Simulates a real government official looking for technical rejection grounds.
Returns a list of specific, actionable objections (max 4).
Empty list = draft passes inspection.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Awaitable

from app.models.case import ClassifiedCase, LegalContext
from app.models.document import LegalPoint

logger = logging.getLogger(__name__)

AiRouterFn = Callable[[str, str], Awaitable[tuple[str, str]]]

_BUREAUCRAT_SYSTEM = """
You are a strict senior government official reviewing a legal complaint/application.
Your job is to find LEGITIMATE technical grounds to reject this application.

You may ONLY raise objections in these 4 categories:
1. MISSING MANDATORY FIELD: A required field is blank, says "Please Fill", or contains a placeholder like "[Your Name]"
2. WRONG LEGAL SECTION: An incorrectly cited law, wrong section number, or inapplicable statute
3. MISSING REQUIRED DOCUMENT: A document that is legally required but not mentioned as enclosed
4. PROCEDURAL ERROR: Wrong authority, wrong court level, wrong form, or wrong jurisdiction

DO NOT raise objections about:
- Style, grammar, or phrasing
- Information that can be reasonably inferred
- Minor omissions that do not affect admissibility

Return ONLY a valid JSON array of strings. Maximum 4 objections.
If the application has no valid grounds for rejection, return: []
No preamble, no explanation outside the JSON array.
"""


async def run_bureaucrat_agent(
    draft: str,
    classified: ClassifiedCase,
    legal_context: LegalContext,
    ai_router_fn: AiRouterFn,
) -> list[str]:
    """
    Returns list of objection strings (max 4).
    Empty list means the draft passed bureaucratic scrutiny.
    """
    logger.info("[bureaucrat] reviewing draft | len=%d case=%s", len(draft), classified.case_type)

    # Also do a quick deterministic pre-check for obvious placeholder gaps
    # (catches them even if AI misses them)
    deterministic_objections = _deterministic_check(draft, legal_context)

    prompt = f"""
Case type: {classified.case_type.value}

Application to review:
---
{draft}
---

Required documents for this case type:
{json.dumps(legal_context.required_documents, indent=2)}

Applicable legal sections that MUST appear:
{json.dumps(legal_context.applicable_sections, indent=2)}

Find all valid rejection grounds. Return ONLY a JSON array.
"""

    ai_objections: list[str] = []
    try:
        response, provider = await ai_router_fn(prompt, "gemini")
        match = re.search(r"\[.*?\]", response, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            ai_objections = [str(o).strip() for o in parsed if o][:4]
            logger.info(
                "[bureaucrat] AI found %d objections | provider=%s",
                len(ai_objections),
                provider,
            )
    except Exception as exc:
        logger.warning("[bureaucrat] AI call failed (%s) — using deterministic only", exc)

    # Merge deterministic + AI, deduplicate, cap at 4
    all_objections = list(dict.fromkeys(deterministic_objections + ai_objections))[:4]
    logger.info("[bureaucrat] total objections=%d", len(all_objections))
    return all_objections


def _deterministic_check(draft: str, legal_context: LegalContext) -> list[str]:
    """
    Fast regex-based check for obvious issues — runs before AI call.
    Never raises exceptions.
    """
    objections: list[str] = []

    # 1. Detect unfilled placeholder markers from document_builder
    please_fill_count = len(re.findall(r"\[.+? — Please Fill\]", draft))
    if please_fill_count > 0:
        objections.append(
            f"{please_fill_count} mandatory field(s) are blank and marked 'Please Fill' — "
            "application cannot be processed until these are completed"
        )

    # 2. Check at least one applicable section is mentioned in the draft
    if legal_context.applicable_sections:
        primary_section = legal_context.applicable_sections[0]
        # Extract just the number/act part for loose matching
        section_fragment = re.sub(r"[^\w\s]", "", primary_section).strip()
        words = section_fragment.split()
        if words and not any(w in draft for w in words if len(w) > 2):
            objections.append(
                f"Applicable legal section '{primary_section}' does not appear to be cited in the document"
            )

    return objections[:2]  # max 2 deterministic objections
