"""
app/integrations/sarvam.py

Sarvam AI STT Client for transcribing Indian language audio.
Wraps the Sarvam REST API, supports 22 languages via Saaras v3.
"""

import logging
import httpx

from app.config import settings
from app.integrations.utils import IntegrationError, retry_with_backoff

logger = logging.getLogger(__name__)

_SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

# 22 official Indian languages mapping to BCP-47 for Saaras v3
_LANG_CODE_MAP = {
    "hi": "hi-IN", "en": "en-IN", "bn": "bn-IN", "ta": "ta-IN", 
    "te": "te-IN", "kn": "kn-IN", "ml": "ml-IN", "mr": "mr-IN", 
    "gu": "gu-IN", "pa": "pa-IN", "or": "or-IN", "as": "as-IN", 
    "ur": "ur-IN", "bho": "bho-IN", "mai": "mai-IN", "sd": "sd-IN",
    "sa": "sa-IN", "ks": "ks-IN", "ne": "ne-IN", "sat": "sat-IN",
    "kok": "kok-IN", "mni": "mni-IN", "doi": "doi-IN", "brx": "brx-IN"
}

@retry_with_backoff(max_retries=2)
async def transcribe_audio(audio_bytes: bytes, lang_hint: str = "hi") -> tuple[str, str, float]:
    """
    Sends audio to Sarvam AI STT.
    Returns:
        (transcript, detected_language, confidence_score)
    """
    if not settings.sarvam_api_key:
        raise IntegrationError(
            "Configuration error: SARVAM_API_KEY is not set in this environment. "
            "Please configure your Sarvam AI API key to use voice intake."
        )
        
    language_code = _LANG_CODE_MAP.get(lang_hint.lower(), "hi-IN")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _SARVAM_STT_URL,
                headers={"api-subscription-key": settings.sarvam_api_key},
                files={"file": ("recording.webm", audio_bytes, "audio/webm")},
                data={
                    "model": "saaras:v3",
                    "language_code": language_code,
                },
            )
            
            if response.status_code == 429:
                raise IntegrationError("Rate limit exceeded for Sarvam API. Please try again later.")
                
            response.raise_for_status()
            data = response.json()
            
            transcript = data.get("transcript") or data.get("text") or ""
            detected_lang = data.get("language_code", language_code)
            
            if not transcript.strip():
                raise IntegrationError("Sarvam returned an empty transcript. Please speak more clearly.")
                
            # Safely get confidence score or mock it if missing
            confidence = float(data.get("confidence", 0.95))
            
            return transcript.strip(), detected_lang, confidence
            
    except httpx.HTTPStatusError as exc:
        logger.warning(f"[sarvam] HTTP error {exc.response.status_code}: {exc.response.text[:200]}")
        raise IntegrationError(f"Failed to transcribe audio via Sarvam: HTTP {exc.response.status_code}")
    except httpx.RequestError as exc:
        logger.warning(f"[sarvam] Network request failed: {exc}")
        raise IntegrationError(f"Failed to connect to Sarvam API: {exc}")
