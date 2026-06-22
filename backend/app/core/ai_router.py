"""
app/core/ai_router.py

AI Router — dispatches to Gemini 2.5 Flash (free), Groq Llama (fallback),
or Claude Sonnet 4 (premium) with automatic fallback chain.

Tier 3 (free):    gemini-2.5-flash → groq llama-3.3-70b → raise
Tier 4 (premium): claude-sonnet-4  → gemini → groq → raise

All clients initialised at module level for connection pooling.
API keys are never logged.
"""

from __future__ import annotations

import json
import logging
import re
import time
import asyncio
from typing import Literal, Callable, Awaitable

import httpx
from anthropic import AsyncAnthropic
from groq import AsyncGroq

from app.config import settings
from app.models.case import ClassifiedCase
from app.models.document import LegalDocument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level clients (connection pooling)
# ---------------------------------------------------------------------------

_groq_client: AsyncGroq | None = None
_anthropic_client: AsyncAnthropic | None = None
_http_client: httpx.AsyncClient | None = None


def _groq() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.groq_api_key)
    return _groq_client


def _anthropic() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

TIER3_SYSTEM = """
You are a legal AI assistant helping Indian citizens access their rights.
You are working within a multi-agent system where deterministic algorithms have already
classified the case and identified applicable laws.

Your role is language generation and reasoning ONLY:
- Write clear, actionable legal text
- Use formal but accessible language
- For any Hindi output: use proper Devanagari script (not romanized)
- Return ONLY the format asked for (JSON or plain text)
- Never add preamble, markdown headers, or explanations
- Never diagnose beyond what the user stated
- Always recommend consulting a lawyer for complex matters
"""

TIER4_SYSTEM = """
You are a senior advocate reviewing an Indian citizen's legal complaint.
The case has been classified and a document drafted by an adversarial AI system.

Your task is to:
1. Write a 2-sentence plain-language summary for the user (English)
2. Write the same in Hindi (Devanagari)
3. Write a 30-word note for a lawyer reviewing this case
4. List 3 concrete next steps the user should take after filing

Return ONLY valid JSON:
{
  "summary": "...",
  "summary_hindi": "...",
  "lawyer_note": "...",
  "next_steps": ["step 1", "step 2", "step 3"]
}
Never add markdown. Return only the JSON object.
"""

_FREE_ENRICH_SYSTEM = """
You are a legal assistant helping an Indian citizen understand their filed legal document.
Return ONLY valid JSON — no preamble, no markdown.
"""

# ---------------------------------------------------------------------------
# Gemini 2.5 Flash — REST (no SDK, lighter dependency)
# ---------------------------------------------------------------------------

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


async def call_gemini(
    prompt: str,
    system: str = TIER3_SYSTEM,
    max_tokens: int = 2000,
) -> str:
    """
    Calls Gemini 2.5 Flash via REST.
    Model: gemini-2.5-flash (gemini-1.5-flash is RETIRED — returns 404).
    Raises httpx.HTTPStatusError or ValueError on failure.
    """
    if settings.use_google_cloud:
        return await call_vertex_gemini(prompt, system, max_tokens)

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    body = {
        "contents": [
            {"parts": [{"text": f"{system}\n\n{prompt}"}]}
        ],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }

    resp = await _http().post(
        _GEMINI_URL,
        params={"key": settings.gemini_api_key},
        json=body,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Unexpected Gemini response structure: {exc}") from exc


async def call_vertex_gemini(
    prompt: str,
    system: str = TIER3_SYSTEM,
    max_tokens: int = 2000,
) -> str:
    """
    Google Meet the Builders path: Gemini 2.5 Flash via Vertex AI.
    Imports are lazy so the default IIT path does not require Google SDKs.
    """
    if not settings.gcp_project:
        raise ValueError("GCP_PROJECT not configured")

    def _generate() -> str:
        import vertexai
        from vertexai.generative_models import GenerativeModel, GenerationConfig

        vertexai.init(project=settings.gcp_project, location=settings.gcp_location)
        model = GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            f"{system}\n\n{prompt}",
            generation_config=GenerationConfig(max_output_tokens=max_tokens),
        )
        text = getattr(response, "text", "") or ""
        if not text:
            raise ValueError("Vertex AI Gemini returned empty content")
        return text

    return await asyncio.to_thread(_generate)


# ---------------------------------------------------------------------------
# Groq — Llama 3.3 70B (free fallback)
# ---------------------------------------------------------------------------


async def call_groq(
    prompt: str,
    system: str = TIER3_SYSTEM,
    max_tokens: int = 2000,
) -> str:
    """
    Calls Groq Llama-3.3-70b-versatile.
    Free tier: 30 RPM, 6000 TPM.
    Raises on any API error.
    """
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY not configured")

    completion = await _groq().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("Groq returned empty content")
    return content


# ---------------------------------------------------------------------------
# Claude Sonnet 4 — premium only
# ---------------------------------------------------------------------------


async def call_claude(
    prompt: str,
    system: str = TIER4_SYSTEM,
    max_tokens: int = 1000,
) -> str:
    """
    Calls Claude Sonnet 4 (claude-sonnet-4-20250514).
    Used only for premium users (Tier 4).
    Raises on any API error.
    """
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    message = await _anthropic().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    content = message.content[0].text if message.content else ""
    if not content:
        raise ValueError("Claude returned empty content")
    return content


# ---------------------------------------------------------------------------
# Fallback dispatcher
# ---------------------------------------------------------------------------


async def call_with_fallback(
    prompt: str,
    preferred: Literal["gemini", "claude"],
    system: str = TIER3_SYSTEM,
    max_tokens: int = 2000,
) -> tuple[str, str]:
    """
    Dispatches with automatic fallback. Returns (response_text, provider_used).

    Tier 3 (free):    gemini → groq → raise
    Tier 4 (premium): claude → gemini → groq → raise

    Logs each attempt with latency. Never logs API keys.
    """
    providers: list[tuple[str, Callable]] = []

    if preferred == "claude":
        providers = [
            ("claude", lambda: call_claude(prompt, system, min(max_tokens, 1000))),
            ("gemini", lambda: call_gemini(prompt, system, max_tokens)),
            ("groq",   lambda: call_groq(prompt, system, max_tokens)),
        ]
    else:
        providers = [
            ("gemini", lambda: call_gemini(prompt, system, max_tokens)),
            ("groq",   lambda: call_groq(prompt, system, max_tokens)),
        ]

    last_exc: Exception | None = None
    for provider_name, call_fn in providers:
        t0 = time.perf_counter()
        try:
            response = await call_fn()
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "[ai_router] OK | provider=%s latency=%dms prompt_len=%d",
                provider_name,
                latency_ms,
                len(prompt),
            )
            return response, provider_name
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "[ai_router] FAIL | provider=%s latency=%dms err=%s",
                provider_name,
                latency_ms,
                type(exc).__name__,   # no API keys in logs
            )
            last_exc = exc
            continue

    raise RuntimeError(
        f"All AI providers failed (preferred={preferred}). Last error: {last_exc}"
    )


# ---------------------------------------------------------------------------
# Document summary enrichment — called by ai_enrich node in debate_graph.py
# ---------------------------------------------------------------------------

_FREE_SUMMARY_PROMPT = """\
You are helping an Indian citizen understand their legal complaint document.

Case type: {case_type}
Applicable sections: {sections}

Document (first 800 chars):
{document_snippet}

Return ONLY this JSON (no markdown, no preamble):
{{
  "summary": "<2 sentences in simple English explaining what the document does>",
  "summary_hindi": "<same 2 sentences in Hindi Devanagari script>",
  "filing_instructions_hindi": "<one sentence in Hindi: where and how to file this document>",
  "next_steps": ["<step 1>", "<step 2>", "<step 3>"]
}}
"""

_PREMIUM_SUMMARY_PROMPT = """\
Case type: {case_type}
Applicable sections: {sections}
Authority to file: {authority}

Document:
---
{document_body}
---

Provide deep legal analysis. Return ONLY this JSON:
{{
  "summary": "<2-sentence plain English summary for the citizen>",
  "summary_hindi": "<same in Hindi Devanagari>",
  "filing_instructions_hindi": "<one Hindi sentence on where/how to file>",
  "lawyer_note": "<30-word clinical note for a reviewing lawyer>",
  "next_steps": ["<step 1>", "<step 2>", "<step 3>"]
}}
"""


def _safe_parse_json(text: str) -> dict:
    """Extract and parse JSON from AI response, stripping markdown fences."""
    # Remove ```json ... ``` fences
    clean = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    # Extract first JSON object
    match = re.search(r"\{[\s\S]*\}", clean)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON object found in AI response: {text[:200]}")


async def generate_document_summary(
    document: LegalDocument,
    classified: ClassifiedCase,
    tier: str = "free",
    ai_router_fn=None,  # optional override for tests
) -> dict:
    """
    Called by the ai_enrich node in debate_graph.py after filing_agent completes.

    FREE tier  → Gemini → Groq: fills summary (EN+HI), filing_instructions_hindi, next_steps
    PREMIUM    → Claude → Gemini → Groq: fills all fields + lawyer_note

    Returns a dict suitable for LegalDocument.model_copy(update=...).
    Never raises — returns empty dict on total failure so the pipeline continues.
    """
    # Use injected router for tests, otherwise use real call_with_fallback
    router = ai_router_fn if ai_router_fn is not None else call_with_fallback

    empty_result: dict = {
        "summary": "",
        "summary_hindi": "",
        "filing_instructions_hindi": "",
        "next_steps": [],
        "lawyer_note": "",
    }

    sections_str = ", ".join(document.applicable_sections[:3]) if document.applicable_sections else "N/A"

    try:
        if tier == "premium":
            prompt = _PREMIUM_SUMMARY_PROMPT.format(
                case_type=document.case_type.value,
                sections=sections_str,
                authority=document.authority_to_file,
                document_body=document.document_body[:1500],
            )
            system = TIER4_SYSTEM
            preferred = "claude"
        else:
            prompt = _FREE_SUMMARY_PROMPT.format(
                case_type=document.case_type.value,
                sections=sections_str,
                document_snippet=document.document_body[:800],
            )
            system = _FREE_ENRICH_SYSTEM
            preferred = "gemini"

        response_text, provider = await router(prompt, preferred, system, 600)
        logger.info("[ai_enrich] provider=%s tier=%s", provider, tier)

        data = _safe_parse_json(response_text)

        return {
            "summary": str(data.get("summary", "")),
            "summary_hindi": str(data.get("summary_hindi", "")),
            "filing_instructions_hindi": str(data.get("filing_instructions_hindi", "")),
            "next_steps": [str(s) for s in data.get("next_steps", [])[:3]],
            "lawyer_note": str(data.get("lawyer_note", "")) if tier == "premium" else "",
            "provider_used": provider,
        }

    except Exception as exc:
        logger.warning("[ai_enrich] enrichment failed: %s", type(exc).__name__)
        return empty_result
