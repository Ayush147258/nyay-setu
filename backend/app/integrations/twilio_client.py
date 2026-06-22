"""
app/integrations/twilio_client.py

Twilio Client for NyaySetu.
Handles routing final documents to applicants via WhatsApp/SMS and emails to authorities.
Includes 2G/offline fallback logic and handles free-tier rate limits.
"""

import logging
from typing import Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.http.http_client import TwilioHttpClient

from app.config import settings
from app.integrations.utils import IntegrationError, retry_with_backoff

logger = logging.getLogger(__name__)

# Module-level client to reuse connection
_twilio_client: Optional[Client] = None

def get_twilio_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise IntegrationError("TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN not configured.")
        # Configure a strict 10s timeout per prompt requirements
        http_client = TwilioHttpClient(timeout=10.0)
        _twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token, http_client=http_client)
    return _twilio_client

@retry_with_backoff(max_retries=2)
async def send_whatsapp(to_number: str, text: str, media_url: Optional[str] = None) -> bool:
    """Sends a WhatsApp message using Twilio Sandbox/API."""
    try:
        client = get_twilio_client()
        kwargs = {
            "from_": f"whatsapp:{settings.twilio_phone_number}",
            "body": text,
            "to": f"whatsapp:{to_number}"
        }
        if media_url:
            kwargs["media_url"] = [media_url]
            
        # Using a thread to not block the async event loop during the synchronous SDK call
        import asyncio
        message = await asyncio.to_thread(lambda: client.messages.create(**kwargs))
        logger.info(f"[twilio] WhatsApp sent to {to_number}, SID: {message.sid}")
        return True
    except TwilioRestException as e:
        logger.error(f"[twilio] WhatsApp failed: {e.msg} (Code: {e.code})")
        # Handle free-tier limits / unverified numbers explicitly (fail fast)
        if e.code in [21614, 21211, 21408]: 
            raise IntegrationError(f"WhatsApp delivery failed: {e.msg}")
        raise IntegrationError(f"WhatsApp transient error: {e.msg}")
    except Exception as e:
        logger.error(f"[twilio] WhatsApp unexpected error: {e}")
        raise IntegrationError(f"WhatsApp unexpected error: {e}")

@retry_with_backoff(max_retries=2)
async def send_sms(to_number: str, text: str) -> bool:
    """Sends a standard SMS message."""
    try:
        client = get_twilio_client()
        import asyncio
        message = await asyncio.to_thread(lambda: client.messages.create(
            from_=settings.twilio_phone_number,
            body=text,
            to=to_number
        ))
        logger.info(f"[twilio] SMS sent to {to_number}, SID: {message.sid}")
        return True
    except TwilioRestException as e:
        logger.error(f"[twilio] SMS failed: {e.msg} (Code: {e.code})")
        if e.code in [21614, 21211]:
            raise IntegrationError(f"SMS delivery failed: Invalid number {to_number}")
        raise IntegrationError(f"SMS transient error: {e.msg}")
    except Exception as e:
        logger.error(f"[twilio] SMS unexpected error: {e}")
        raise IntegrationError(f"SMS unexpected error: {e}")

async def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    Stub for Email integration. 
    In production, this routes the formal petition to the authority.
    """
    logger.info(f"[twilio] Email sent to {to_email} | Subject: {subject}")
    # Implementation using sendgrid would go here. We simulate success.
    return True

async def dispatch_with_2g_fallback(to_number: str, text: str, case_id: str) -> bool:
    """
    Attempts to send rich message (WhatsApp).
    If it fails (e.g. unverified number on free tier, or network failure),
    falls back to plain-text 2G SMS.
    """
    logger.info(f"[twilio] Dispatching update for Case {case_id} to {to_number}")
    
    # 1. Try Rich Channel
    try:
        success = await send_whatsapp(to_number, text)
        if success:
            return True
    except IntegrationError as e:
        logger.warning(f"[twilio] WhatsApp exception: {e}")
        
    # 2. 2G/Offline Absolute Fallback
    logger.warning(f"[twilio] Rich channel failed for Case {case_id}. Triggering 2G/Offline SMS fallback.")
    fallback_text = f"NyaySetu: Your petition (Ref: {case_id[-6:]}) is ready. We could not reach you on WhatsApp. Please call 1800-NYAY-HELP (toll-free) to get your document."
    
    try:
        sms_success = await send_sms(to_number, fallback_text)
        if not sms_success:
            logger.error(f"[twilio] Absolute fallback SMS also failed for Case {case_id}.")
            return False
        return True
    except IntegrationError as e:
        logger.error(f"[twilio] Fallback SMS exception: {e}")
        return False
