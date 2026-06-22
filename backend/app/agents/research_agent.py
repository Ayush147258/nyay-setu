"""
app/agents/research_agent.py

Research Agent — fetches relevant laws and precedents from IndianKanoon API.
Uses Upstash Redis to cache results for 24 hours (zero repeat API calls).
Falls back gracefully to static case_types.json data on any API failure.
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from app.config import settings
from app.core.case_classifier import get_legal_context, load_case_db
from app.models.case import CaseType, ClassifiedCase, LegalContext

logger = logging.getLogger(__name__)

_IKANOON_BASE = "https://api.indiankanoon.org"
_CACHE_TTL_SECONDS = 86400  # 24 hours

# Search queries per case type — tuned for best IndianKanoon results
_SEARCH_QUERIES: dict[CaseType, str] = {
    CaseType.FIR_REFUSAL: "Section 156(3) CrPC magistrate direct FIR refusal police",
    CaseType.CROP_INSURANCE: "PMFBY crop insurance rejection appeal farmer India",
    CaseType.FLOOD_RELIEF: "SDRF disaster relief flood compensation District Collector",
    CaseType.WAGE_THEFT: "Payment of Wages Act unpaid salary employer labour court",
    CaseType.RTI_REQUEST: "Right to Information Act Section 6 public information officer",
    CaseType.CONSUMER_COMPLAINT: "Consumer Protection Act 2019 defective product refund forum",
    CaseType.LAND_DISPUTE: "illegal encroachment land property criminal trespass IPC 441",
    CaseType.DOMESTIC_VIOLENCE: "Protection of Women Domestic Violence Act 2005 Section 12",
    CaseType.LABOUR_COMPLAINT: "Labour Code 2020 minimum wages factory worker rights",
    CaseType.UNKNOWN: "legal rights India citizen grievance",
}


def _redis_client():
    """Lazy-import Upstash Redis to avoid import errors if not configured."""
    try:
        from upstash_redis import Redis  # type: ignore
        if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
            return Redis(
                url=settings.upstash_redis_rest_url,
                token=settings.upstash_redis_rest_token,
            )
    except Exception:
        pass
    return None


async def _fetch_indiankanoon(query: str) -> list[str]:
    """
    POST /search/ to IndianKanoon and return up to 3 headline strings.
    Returns [] on any error.
    """
    if not settings.indiankanoon_api_key:
        logger.warning("[research] IndianKanoon API key not configured — skipping")
        return []

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_IKANOON_BASE}/search/",
                headers={"Authorization": f"Token {settings.indiankanoon_api_key}"},
                json={"formInput": query, "pagenum": 0},
            )
            resp.raise_for_status()
            data = resp.json()
            docs = data.get("docs", [])
            headlines = []
            for doc in docs[:3]:
                headline = doc.get("headline") or doc.get("title") or ""
                # Strip HTML tags from headline
                import re
                clean = re.sub(r"<[^>]+>", "", headline).strip()
                if clean:
                    headlines.append(clean)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "[research] IndianKanoon OK | query=%r latency=%dms results=%d",
                query[:60],
                latency_ms,
                len(headlines),
            )
            return headlines
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning(
            "[research] IndianKanoon FAILED | query=%r latency=%dms err=%s",
            query[:60],
            latency_ms,
            exc,
        )
        return []


async def run_research_agent(classified: ClassifiedCase) -> LegalContext:
    """
    1. Build search query for case_type
    2. Check Redis cache (key: "ikanoon:{case_type}") — TTL 24h
    3. Cache miss → call IndianKanoon API
    4. Extract top 3 headlines as relevant_precedents
    5. Build LegalContext from case_types.json + precedents
    6. Cache result
    7. Return LegalContext
    """
    case_type = classified.case_type
    cache_key = f"ikanoon:{case_type.value}"

    # Build base context from static DB (always available)
    base_context = get_legal_context(case_type, classified.extracted_entities)

    # Try Redis cache first
    redis = _redis_client()
    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                precedents = json.loads(cached)
                logger.info("[research] cache HIT | key=%s", cache_key)
                return base_context.model_copy(update={"relevant_precedents": precedents})
        except Exception as exc:
            logger.warning("[research] Redis GET failed: %s", exc)

    # Cache miss — fetch from IndianKanoon
    query = _SEARCH_QUERIES.get(case_type, _SEARCH_QUERIES[CaseType.UNKNOWN])
    precedents = await _fetch_indiankanoon(query)

    # Store in Redis with 24h TTL
    if redis and precedents:
        try:
            redis.setex(cache_key, _CACHE_TTL_SECONDS, json.dumps(precedents))
            logger.info("[research] cache SET | key=%s ttl=%ds", cache_key, _CACHE_TTL_SECONDS)
        except Exception as exc:
            logger.warning("[research] Redis SET failed: %s", exc)

    return base_context.model_copy(update={"relevant_precedents": precedents})
