"""
app/db/neon_client.py

Async Neon PostgreSQL client using asyncpg (no ORM — Prisma handles the frontend).
All public functions are fire-and-forget safe: they never raise, they log and return None.

Connection: asyncpg connection pool (min=2, max=10).
SSL: required for Neon (ssl="require" passed to asyncpg).
"""

from __future__ import annotations

import json
import logging
import uuid
import asyncio
import datetime

import asyncpg

from app.config import settings
from app.models.document import LegalDocument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool — module-level singleton
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """
    Returns the shared asyncpg connection pool, creating it on first call.
    Neon requires ssl="require" — passed as ssl kwarg to asyncpg (not in DSN).
    """
    global _pool
    if _pool is None:
        # Strip any existing sslmode param from DSN to avoid conflicts,
        # then pass ssl="require" as a kwarg — asyncpg's preferred way.
        dsn = settings.database_url
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=2,
            max_size=10,
            command_timeout=30,
            ssl="require",
            # Register a JSON codec so asyncpg automatically decodes JSONB
            init=_register_codecs,
        )
        logger.info("[neon] connection pool created (min=2 max=10)")
    return _pool


async def _register_codecs(conn: asyncpg.Connection) -> None:
    """Register JSON/JSONB codecs for automatic Python dict encoding/decoding."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def close_pool() -> None:
    """Gracefully close the pool (call on app shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("[neon] connection pool closed")


# ---------------------------------------------------------------------------
# Case persistence
# ---------------------------------------------------------------------------


async def save_case(
    document: LegalDocument,
    user_id: str | None = None,
    detected_language: str = "en",
) -> str | None:
    """
    Saves a LegalDocument to the cases table.
    Returns the new case UUID string, or None on any failure.
    Never raises — errors are logged and swallowed so the API response is never blocked.
    """
    if settings.use_google_cloud:
        return await save_case_firestore(document, user_id, detected_language)

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO cases (
                    user_id,
                    case_type,
                    detected_language,
                    original_text,
                    document_title,
                    document_body,
                    document_status,
                    confidence_score,
                    has_unresolved_gaps,
                    total_debate_rounds,
                    mediator_override_triggered,
                    tier_used,
                    provider_used,
                    document_json,
                    processing_time_ms
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    $10, $11, $12, $13, $14, $15
                )
                RETURNING id
                """,
                # $1  user_id — cast to UUID or None
                uuid.UUID(user_id) if user_id else None,
                # $2  case_type
                document.case_type.value,
                # $3  detected_language
                detected_language,
                # $4  original_text — not stored in LegalDocument; set externally if needed
                None,
                # $5  document_title
                document.document_title,
                # $6  document_body
                document.document_body,
                # $7  document_status
                document.status.value,
                # $8  confidence_score
                document.confidence_score,
                # $9  has_unresolved_gaps
                len(document.unresolved_gaps) > 0,
                # $10 total_debate_rounds
                document.total_rounds,
                # $11 mediator_override_triggered
                document.mediator_override_triggered,
                # $12 tier_used
                document.tier_used.value,
                # $13 provider_used
                document.provider_used,
                # $14 document_json (JSONB — codec encodes the dict automatically)
                document.model_dump(mode="json"),
                # $15 processing_time_ms
                document.processing_time_ms,
            )
            case_id = str(row["id"]) if row else None
            logger.info("[neon] save_case OK | id=%s case_type=%s", case_id, document.case_type.value)
            return case_id

    except Exception as exc:
        logger.warning("[neon] save_case FAILED | case_type=%s err=%s", document.case_type.value, exc)
        return None

async def insert_agent_run(
    case_id: str,
    agent_name: str,
    round_number: int,
    input_summary: str,
    output_summary: str,
    score: float | None = None
) -> None:
    """
    Persists an agent transition into the agent_runs table so the Agent Arena UI can replay a full run.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_runs (case_id, agent_name, round_number, input_summary, output_summary, score)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                uuid.UUID(case_id),
                agent_name,
                round_number,
                input_summary,
                output_summary,
                score
            )
            logger.debug(f"[neon] insert_agent_run OK | case_id={case_id} agent={agent_name}")
    except Exception as exc:
        logger.warning(f"[neon] insert_agent_run FAILED | err={exc}")

async def insert_followup(case_id: str, next_check: datetime.datetime, status: str) -> None:
    """
    Inserts a 7-day followup check for a filed case.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO follow_ups (case_id, next_check_at, last_status, escalated)
                VALUES ($1, $2, $3, false)
                """,
                uuid.UUID(case_id),
                next_check,
                status
            )
    except Exception as exc:
        logger.warning(f"[neon] insert_followup FAILED | err={exc}")

# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


async def save_case_firestore(
    document: LegalDocument,
    user_id: str | None = None,
    detected_language: str = "en",
) -> str | None:
    """
    Google Meet the Builders path: persist sessions to Firebase Firestore.
    Imports are lazy so the default Neon path does not require Firebase SDKs.
    """
    try:
        case_id = str(uuid.uuid4())
        payload = {
            "id": case_id,
            "user_id": user_id,
            "case_type": document.case_type.value,
            "detected_language": detected_language,
            "document_title": document.document_title,
            "document_body": document.document_body,
            "document_status": document.status.value,
            "confidence_score": document.confidence_score,
            "has_unresolved_gaps": len(document.unresolved_gaps) > 0,
            "total_debate_rounds": document.total_rounds,
            "mediator_override_triggered": document.mediator_override_triggered,
            "tier_used": document.tier_used.value,
            "provider_used": document.provider_used,
            "document_json": document.model_dump(mode="json"),
            "processing_time_ms": document.processing_time_ms,
        }

        def _write() -> None:
            import firebase_admin
            from firebase_admin import firestore

            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            db = firestore.client()
            db.collection(settings.firestore_cases_collection).document(case_id).set(payload)

        await asyncio.to_thread(_write)
        logger.info("[firestore] save_case OK | id=%s case_type=%s", case_id, document.case_type.value)
        return case_id
    except Exception as exc:
        logger.warning("[firestore] save_case FAILED | case_type=%s err=%s", document.case_type.value, exc)
        return None


async def get_user_tier(user_id: str) -> str:
    """
    Returns 'free' or 'premium'. Returns 'free' on any error (safe default).
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT tier FROM users WHERE id = $1",
                uuid.UUID(user_id),
            )
            tier = row["tier"] if row else "free"
            logger.debug("[neon] get_user_tier | user=%s tier=%s", user_id[:8], tier)
            return tier
    except Exception as exc:
        logger.warning("[neon] get_user_tier FAILED | err=%s", exc)
        return "free"


async def upsert_user(
    user_id: str,
    email: str | None = None,
    name: str | None = None,
) -> bool:
    """
    Creates or updates a user row. Called after JWT verification in /analyze.
    Returns True on success, False on failure.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, email, name)
                VALUES ($1, $2, $3)
                ON CONFLICT (id) DO UPDATE
                    SET email = COALESCE(EXCLUDED.email, users.email),
                        name  = COALESCE(EXCLUDED.name, users.name),
                        updated_at = NOW()
                """,
                uuid.UUID(user_id),
                email,
                name,
            )
            await conn.execute(
                "UPDATE users SET cases_analyzed = cases_analyzed + 1 WHERE id = $1",
                uuid.UUID(user_id),
            )
            return True
    except Exception as exc:
        logger.warning("[neon] upsert_user FAILED | err=%s", exc)
        return False


async def upgrade_user_to_premium(user_id: str, plan: str = "per_report") -> bool:
    """
    Sets tier='premium' after successful payment verification.
    plan='monthly' → sets premium_expires_at to 30 days from now.
    plan='per_report' → no expiry set.
    """
    try:
        import datetime
        pool = await get_pool()
        async with pool.acquire() as conn:
            if plan == "monthly":
                expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
                await conn.execute(
                    """
                    UPDATE users
                    SET tier = 'premium', premium_expires_at = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    uuid.UUID(user_id),
                    expires_at,
                )
            else:
                await conn.execute(
                    "UPDATE users SET tier = 'premium', updated_at = NOW() WHERE id = $1",
                    uuid.UUID(user_id),
                )
        logger.info("[neon] upgrade_user_to_premium OK | user=%s plan=%s", user_id[:8], plan)
        return True
    except Exception as exc:
        logger.warning("[neon] upgrade_user_to_premium FAILED | err=%s", exc)
        return False


# ---------------------------------------------------------------------------
# Case retrieval
# ---------------------------------------------------------------------------


async def get_user_cases(user_id: str, limit: int = 10) -> list[dict]:
    """
    Returns recent cases for a user (for dashboard history).
    Returns [] on any failure.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id::text,
                    case_type,
                    document_title,
                    document_status,
                    confidence_score,
                    has_unresolved_gaps,
                    total_debate_rounds,
                    tier_used,
                    created_at
                FROM cases
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                uuid.UUID(user_id),
                limit,
            )
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("[neon] get_user_cases FAILED | err=%s", exc)
        return []


async def get_case_by_id(case_id: str) -> dict | None:
    """
    Returns the full case row (including document_json) by case UUID.
    Returns None on not found or any failure.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM cases WHERE id = $1",
                uuid.UUID(case_id),
            )
            return dict(row) if row else None
    except Exception as exc:
        logger.warning("[neon] get_case_by_id FAILED | id=%s err=%s", case_id, exc)
        return None
