"""
app/agents/advocate_agent.py

Advocate Agent — drafts the initial legal document.
Step 1: Deterministic template fill (zero LLM)
Step 2: AI enhancement to make facts specific (Gemini/Groq/Claude)
Returns a string: the draft document text.
"""

from __future__ import annotations

import logging
from typing import Callable, Awaitable

from app.models.case import ClassifiedCase, LegalContext
from app.core.document_builder import build_initial_document

logger = logging.getLogger(__name__)

# Type alias for the injected AI router function
AiRouterFn = Callable[[str, str], Awaitable[tuple[str, str]]]

_ADVOCATE_SYSTEM = """
You are a senior legal aid advocate helping an Indian citizen draft a legal complaint.
You receive a pre-filled template document and the user's original statement.
Your ONLY job is to improve the facts section and prayer — do NOT change any cited
legal sections or procedural structure.

Rules:
- Make the facts section more specific using details from the user's statement
- Add inferable details (do NOT invent facts not in the user's statement)
- Strengthen the prayer/relief section
- Keep the formal legal tone
- Return ONLY the improved document text — no preamble, no markdown, no explanation
"""


async def run_advocate_agent(
    classified: ClassifiedCase,
    legal_context: LegalContext,
    ai_router_fn: AiRouterFn,
    use_ai: bool = True,
) -> str:
    """
    Returns the advocate's draft document as a plain string.

    use_ai=False → pure deterministic template (useful in tests / fallback).
    use_ai=True  → template + AI enhancement via Gemini → Groq fallback.
    """
    logger.info("[advocate] building draft | case_type=%s use_ai=%s", classified.case_type, use_ai)

    # Step 1 — deterministic template fill (always done first)
    initial_draft = build_initial_document(
        classified.case_type,
        classified.extracted_entities,
        legal_context,
        user_name=classified.user_name,
        user_location=classified.user_location,
    )

    if not use_ai:
        logger.info("[advocate] use_ai=False — returning template draft")
        return initial_draft

    # Step 2 — AI enhancement
    prompt = f"""
User's original statement (in their language):
\"\"\"{classified.original_text}\"\"\"

Case type: {classified.case_type.value}

Initial template draft:
---
{initial_draft}
---

Improve this draft following the rules in your system prompt.
Return ONLY the improved document text.
"""

    try:
        improved, provider = await ai_router_fn(prompt, "gemini")
        if improved and len(improved) > 100:
            logger.info("[advocate] AI enhanced draft | provider=%s len=%d", provider, len(improved))
            return improved
        logger.warning("[advocate] AI returned short/empty response — using template draft")
    except Exception as exc:
        logger.warning("[advocate] AI call failed (%s) — falling back to template draft", exc)

    return initial_draft
