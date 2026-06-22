"""
app/agents/intake.py

Intake Agent Node for the LangGraph Orchestrator.
Responsibilities:
- Accept raw text or audio file reference.
- Call Sarvam AI STT if audio.
- Normalize transcript using LLM router.
- Classify case type with confidence score and legal provision.
- If confidence is below threshold, ask a clarifying question.
"""

from __future__ import annotations

import logging
import time

from app.agents.state import CaseState
from app.integrations.sarvam import transcribe_audio
from app.core.ai_router import call_with_fallback
from app.core.case_classifier import classify_case_llm

logger = logging.getLogger(__name__)

_NORMALIZE_SYSTEM = """
You are a transcript normalizer. Your job is to take raw, spoken complaints 
(which may contain filler words, transcription artifacts, or stuttering) 
and return a clean, highly readable version of the complaint.
Keep all factual details intact. If the input is clear, return it mostly unchanged.
Return ONLY the cleaned text. No preamble, no quotes.
"""

async def _normalize_transcript(text: str) -> str:
    """Uses LLM to strip filler words and fix obvious artifacts."""
    try:
        clean_text, _ = await call_with_fallback(
            prompt=text,
            preferred="gemini",
            system=_NORMALIZE_SYSTEM,
            max_tokens=1000
        )
        return clean_text.strip()
    except Exception as e:
        logger.warning(f"[intake] Normalization failed, using original text: {e}")
        return text

async def intake_node(state: CaseState) -> dict:
    """
    LangGraph node function.
    Matches the exact signature expected by the graph (state in, partial state update out).
    """
    t0 = time.perf_counter()
    
    # Safely retrieve timestamps or initialize
    timestamps = state.get("timestamps", {})
    timestamps["intake_start"] = t0
    
    raw_input = state.get("raw_input", "")
    detected_lang = state.get("detected_language", "en")
    
    # 1. Accept audio file reference or raw text
    if raw_input.startswith("audio:"):
        file_path = raw_input.split("audio:", 1)[1]
        try:
            with open(file_path, "rb") as f:
                audio_bytes = f.read()
            # Call Sarvam AI STT
            raw_input, detected_lang, _ = await transcribe_audio(audio_bytes, lang_hint="hi")
            logger.info(f"[intake] Audio transcribed. Lang: {detected_lang}")
        except Exception as e:
            logger.error(f"[intake] Audio transcription failed: {e}")
            raise ValueError(f"Audio transcription failed: {e}")
            
    # 2. Normalize the transcript
    normalized_text = await _normalize_transcript(raw_input)
    
    # 3. Classify case type with legal provision
    case_type, confidence, legal_provision = await classify_case_llm(normalized_text)
    
    logger.info(f"[intake] Classified: {case_type} | Conf: {confidence:.2f} | Law: {legal_provision}")
    
    # Prepare partial state update
    updates: dict = {
        "raw_input": normalized_text,
        "detected_language": detected_lang,
        "case_type": case_type,
        "classification_confidence": confidence,
        "_legal_provision": legal_provision,
        "timestamps": timestamps
    }
    
    # 4. Confidence Threshold Check
    CONFIDENCE_THRESHOLD = 0.6
    if confidence < CONFIDENCE_THRESHOLD:
        logger.warning(f"[intake] Confidence too low ({confidence}). Asking clarifying question.")
        updates["clarifying_question"] = (
            f"I'm having trouble understanding the exact legal issue. "
            f"I think it might be related to '{case_type}', but I need more details. "
            f"Could you please explain what happened again with specific facts, dates, and names?"
        )
    else:
        # Clear any previous clarifying question if confidence is good
        updates["clarifying_question"] = None
        
    timestamps["intake_end"] = time.perf_counter()
    return updates
