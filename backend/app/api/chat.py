"""
app/api/chat.py

POST /api/chat — contextual chat about a filed legal document.
Supports Hindi, English, and Hinglish input.
Free tier: max 10 messages per session.
Premium tier: Claude → Gemini → Groq unlimited.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from app.core.ai_router import call_with_fallback, TIER3_SYSTEM
from app.models.document import ChatRequest, ChatResponse, LegalDocument

router = APIRouter()
logger = logging.getLogger(__name__)

_FREE_MSG_LIMIT = 10

_LIMIT_MESSAGES = {
    "en": "Free chat limit reached (10 messages). Upgrade for unlimited chat.",
    "hi": "आपकी 10 free messages समाप्त हो गई हैं। अधिक chat के लिए upgrade करें।",
}

_FALLBACK_REPLIES = {
    "en": "I'm having trouble connecting right now. Please try again in a moment.",
    "hi": "अभी कनेक्शन में समस्या है। कृपया थोड़ी देर बाद पुनः प्रयास करें।",
}

_CHAT_SYSTEM_TEMPLATE = """\
You are a legal assistant helping an Indian citizen understand their legal complaint.
The user may write in Hindi, English, or Hinglish — understand all three.

Their case:
- Type: {case_type}
- Status: {status}
- Document (first 500 chars): {document_snippet}...
- Applicable laws: {applicable_sections}
- Unresolved gaps (fields they still need to fill): {unresolved_gaps}

Rules:
- Answer in {lang_instruction}
- Keep your reply under 80 words
- Never give definitive legal advice or diagnose the case outcome
- Recommend consulting a lawyer for complex decisions
- Be warm and supportive — the user may be distressed
- If asked about the unresolved gaps, explain what the user needs to provide
"""


async def chat(request: ChatRequest) -> ChatResponse:
    lang = request.lang.lower().strip()
    if lang not in ("en", "hi"):
        lang = "en"

    # ── Validate ──────────────────────────────────────────────────────────
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    # ── Parse document_data ───────────────────────────────────────────────
    try:
        doc_dict = json.loads(request.document_data)
        document = LegalDocument(**doc_dict)
    except Exception as exc:
        logger.warning("[chat] failed to parse document_data: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid document_data — must be a JSON-stringified LegalDocument.")

    # ── Rate limit for free tier ──────────────────────────────────────────
    tier = request.tier.lower().strip()
    user_message_count = sum(1 for m in request.messages if m.role == "user")
    if tier == "free" and user_message_count > _FREE_MSG_LIMIT:
        limit_msg = _LIMIT_MESSAGES.get(lang, _LIMIT_MESSAGES["en"])
        return ChatResponse(reply=limit_msg, lang=lang)

    # ── Build system prompt ───────────────────────────────────────────────
    lang_instruction = "Hindi (Devanagari script only — no romanized Hindi)" if lang == "hi" else "simple Indian English"
    unresolved_fields = [g.field for g in document.unresolved_gaps] if document.unresolved_gaps else []

    system = _CHAT_SYSTEM_TEMPLATE.format(
        case_type=document.case_type.value,
        status=document.status.value,
        document_snippet=document.document_body[:500],
        applicable_sections=", ".join(document.applicable_sections) or "N/A",
        unresolved_gaps=unresolved_fields or "None",
        lang_instruction=lang_instruction,
    )

    # Build message history for the AI call (last 10 messages to stay within token limits)
    history_text = "\n".join(
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
        for m in request.messages[-10:]
    )
    prompt = f"Conversation history:\n{history_text}\n\nRespond to the user's latest message."

    # ── Call AI ───────────────────────────────────────────────────────────
    preferred = "claude" if tier == "premium" else "gemini"
    try:
        reply, provider = await call_with_fallback(
            prompt=prompt,
            preferred=preferred,
            system=system,
            max_tokens=300,
        )
        logger.info("[chat] OK | provider=%s tier=%s lang=%s msgs=%d", provider, tier, lang, user_message_count)
        return ChatResponse(reply=reply.strip(), lang=lang)
    except Exception as exc:
        logger.warning("[chat] all providers failed: %s", exc)
        fallback = _FALLBACK_REPLIES.get(lang, _FALLBACK_REPLIES["en"])
        return ChatResponse(reply=fallback, lang=lang)


router.add_api_route("/chat", chat, methods=["POST"])
