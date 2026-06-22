"""
app/agents/mediator_agent.py

Mediator Agent — the final authority in the adversarial loop.
Scores objections (valid vs nitpick), patches the document, and
marks what genuinely needs user input as unresolved.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Awaitable

from app.models.case import ClassifiedCase

logger = logging.getLogger(__name__)

AiRouterFn = Callable[[str, str], Awaitable[tuple[str, str]]]

_MEDIATOR_SYSTEM = """
You are a senior judge arbitrating between a legal document drafter and a government official.

Your role:
1. For each objection, decide: VALID (must fix) or REJECTED (nitpick/frivolous/wrong)
2. For VALID objections that can be fixed using context already in the document: patch the document
3. For VALID objections that require information the user must provide: mark as unresolved

Rules:
- Preserve all legal sections cited — never remove or change a statutory reference
- Keep the formal legal tone and structure
- Only annotate gaps with "[FIELD — Please Fill]" markers — never invent facts
- If an objection is about a stylistic issue → REJECTED

Return ONLY this exact JSON structure (no markdown, no preamble):
{
  "patched_document": "<full improved document text>",
  "resolved": ["<objection text that was fixed>"],
  "unresolved": ["<objection text that requires user input>"]
}
"""


async def run_mediator_agent(
    draft: str,
    objections: list[str],
    classified: ClassifiedCase,
    ai_router_fn: AiRouterFn,
) -> tuple[str, list[str], bool]:
    """
    Returns: (patched_draft, unresolved_objections, patch_applied)

    If no objections: returns (draft, [], False) immediately — no AI call.
    """
    if not objections:
        logger.info("[mediator] no objections — passing draft unchanged")
        return draft, [], False

    logger.info("[mediator] arbitrating %d objection(s) | case=%s", len(objections), classified.case_type)

    objections_text = "\n".join(f"- {o}" for o in objections)
    prompt = f"""
Document to review:
---
{draft}
---

Objections raised by the reviewing official:
{objections_text}

Case type: {classified.case_type.value}

Arbitrate each objection and return the patched document + resolution JSON.
"""

    try:
        response, provider = await ai_router_fn(prompt, "gemini")
        logger.info("[mediator] AI responded | provider=%s len=%d", provider, len(response))

        # Extract JSON object — handle code fences and extra text
        # Try strict JSON first, then relaxed regex
        json_match = re.search(r"\{[\s\S]*\}", response)
        if not json_match:
            raise ValueError("No JSON object found in mediator response")

        data = json.loads(json_match.group())
        patched = data.get("patched_document", "").strip()
        resolved: list[str] = [str(r) for r in data.get("resolved", [])]
        unresolved: list[str] = [str(u) for u in data.get("unresolved", [])]

        if not patched or len(patched) < 50:
            logger.warning("[mediator] patched_document too short — keeping original draft")
            patched = draft

        patch_applied = bool(resolved)
        logger.info(
            "[mediator] resolved=%d unresolved=%d patch_applied=%s",
            len(resolved),
            len(unresolved),
            patch_applied,
        )
        return patched, unresolved, patch_applied

    except Exception as exc:
        logger.warning("[mediator] AI call failed (%s) — returning draft with all objections unresolved", exc)
        # Safe fallback: return original draft, all objections unresolved
        return draft, objections, False
