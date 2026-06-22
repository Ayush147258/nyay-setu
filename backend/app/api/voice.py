"""
app/api/voice.py

Thin wrapper exposing integrations/sarvam.py directly for the frontend's
live transcript preview before a full case run is triggered.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import logging

from app.integrations.sarvam import transcribe_audio

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/transcribe")
async def transcribe_voice(
    file: UploadFile = File(...),
    lang_hint: str = Form("hi")
):
    """
    Accepts an audio file and returns the transcript and detected language.
    """
    logger.info(f"[voice] Received audio for transcription, hint={lang_hint}")
    try:
        audio_bytes = await file.read()
        transcript, detected_lang, confidence = await transcribe_audio(audio_bytes, lang_hint)
        return {
            "transcript": transcript,
            "detected_language": detected_lang,
            "confidence": confidence
        }
    except Exception as e:
        logger.error(f"[voice] Transcription failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))
