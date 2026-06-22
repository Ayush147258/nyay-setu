"""
app/agents/intake_agent.py

Intake Agent — classifies incoming text, normalises language, extracts entities.
Wraps app/core/case_classifier.py into an async agent interface.
Zero LLM cost — 100% deterministic.
"""

from __future__ import annotations

import logging

from app.models.case import CaseInput, ClassifiedCase, Language
from app.core.case_classifier import (
    classify_case,
    extract_entities,
    normalize_hinglish,
)

logger = logging.getLogger(__name__)


async def run_intake_agent(input: CaseInput) -> ClassifiedCase:
    """
    Step 1 — Normalize Hinglish
    Step 2 — Classify case type + confidence
    Step 3 — Extract entities (regex, per case type)
    Step 4 — Build and return ClassifiedCase
    """
    logger.info("[intake] starting | text_len=%d lang=%s", len(input.text), input.detected_language)

    # Step 1 — normalise
    normalized_text = normalize_hinglish(input.text)

    # Step 2 — classify
    case_type, confidence = classify_case(input.text)
    logger.info("[intake] classified | case_type=%s confidence=%.2f", case_type, confidence)

    # Step 3 — extract entities using original text (preserves Devanagari)
    entities = extract_entities(input.text, case_type)
    logger.debug("[intake] entities=%s", entities)

    # Detect language from character set if not already set
    detected_lang = input.detected_language
    if detected_lang == Language.EN:
        # Heuristic: if Devanagari characters present → Hindi or Hinglish
        devanagari_chars = sum(1 for c in input.text if "\u0900" <= c <= "\u097F")
        if devanagari_chars > 5:
            detected_lang = Language.HI
        elif devanagari_chars > 0:
            detected_lang = Language.HINGLISH

    return ClassifiedCase(
        original_text=input.text,
        normalized_text=normalized_text,
        case_type=case_type,
        confidence=confidence,
        detected_language=detected_lang,
        extracted_entities=entities,
        user_name=input.user_name,
        user_location=input.user_location,
        tier=input.tier,
    )
