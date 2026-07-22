"""PostgreSQL-backed durable analysis jobs and event persistence."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

import asyncpg
from pydantic import BaseModel, Field

from app.document_intelligence.models import utc_now


class JobStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    RESEARCHING = "researching"
    SYNTHESIZING = "synthesizing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATUSES = {
    JobStatus.EXTRACTING,
    JobStatus.RESEARCHING,
    JobStatus.SYNTHESIZING,
    JobStatus.VERIFYING,
}
TERMINAL_JOB_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.NEEDS_REVIEW,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}


class JobConflict(RuntimeError):
    """Raised when a job control operation is invalid for its current state."""


class AnalysisJobRecord(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    tenant_id: str = "default"
    requested_by_user_id: uuid.UUID | None = None
    status: JobStatus
    workflow_version: str
    idempotency_key: str
    document_version_ids: list[str]
    document_hashes: list[str]
    enable_external_research: bool = False
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    available_at: datetime
    leased_until: datetime | None = None
    worker_id: str | None = None
    cancel_requested_at: datetime | None = None
    run_id: str | None = None
    report_id: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> "AnalysisJobRecord":
        return cls.model_validate(dict(row))


class AnalysisJobEvent(BaseModel):
    id: int
    job_id: uuid.UUID
    sequence: int = Field(ge=0)
    event_type: str
    status: JobStatus
    agent: str | None = None
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> "AnalysisJobEvent":
        return cls.model_validate(dict(row))


class AnalysisArtifact(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    case_id: uuid.UUID
    artifact_type: str
    artifact_id: str
    reference_uri: str
    sha256: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> "AnalysisArtifact":
        return cls.model_validate(dict(row))


class AnalysisJobResponse(BaseModel):
    job_id: uuid.UUID
    case_id: uuid.UUID
    status: JobStatus
    attempts: int
    max_attempts: int
    workflow_version: str
    document_version_ids: list[str]
    enable_external_research: bool
    run_id: str | None = None
    report_id: str | None = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False
    deduplicated: bool = False
    available_at: datetime
    leased_until: datetime | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        job: AnalysisJobRecord,
        *,
        deduplicated: bool = False,
    ) -> "AnalysisJobResponse":
        return cls(
            job_id=job.id,
            case_id=job.case_id,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            workflow_version=job.workflow_version,
            document_version_ids=job.document_version_ids,
            enable_external_research=job.enable_external_research,
            run_id=job.run_id,
            report_id=job.report_id,
            error=job.error,
            cancel_requested=job.cancel_requested_at is not None,
            deduplicated=deduplicated,
            available_at=job.available_at,
            leased_until=job.leased_until,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            updated_at=job.updated_at,
        )


@dataclass(frozen=True)
class EnqueueResult:
    job: AnalysisJobRecord
    created: bool


def build_analysis_idempotency_key(
    *,
    case_id: str,
    tenant_id: str = "default",
    workflow_version: str,
    document_versions: list[tuple[str, str]],
    enable_external_research: bool,
) -> str:
    """Hash the complete immutable analysis input into a stable queue key."""
    canonical = {
        "case_id": case_id,
        "tenant_id": tenant_id,
        "workflow_version": workflow_version,
        "documents": sorted(
            (
                {"version_id": version_id, "sha256": sha256}
                for version_id, sha256 in document_versions
            ),
            key=lambda item: (item["sha256"], item["version_id"]),
        ),
        "enable_external_research": enable_external_research,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def retry_delay_seconds(
    attempt_number: int,
    base_seconds: int,
    max_seconds: int,
) -> int:
    """Return capped exponential backoff for a one-based attempt number."""
    return min(
        base_seconds * (2 ** max(attempt_number - 1, 0)),
        max_seconds,
    )


class AnalysisJobRepositoryProtocol(Protocol):
    async def recover_stale_jobs(
        self,
        limit: int = 100,
    ) -> list[AnalysisJobRecord]: ...

    async def claim_next(
        self,
        worker_id: str,
        lease_seconds: int,
    ) -> AnalysisJobRecord | None: ...

    async def set_stage(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        status: JobStatus,
        *,
        agent: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> AnalysisJobRecord | None: ...

    async def heartbeat(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        lease_seconds: int,
    ) -> bool: ...

    async def is_cancel_requested(self, job_id: uuid.UUID) -> bool: ...

    async def complete(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        *,
        status: JobStatus,
        run_id: str,
        report_id: str,
    ) -> AnalysisJobRecord: ...

    async def mark_cancelled(
        self,
        job_id: uuid.UUID,
        worker_id: str,
    ) -> AnalysisJobRecord: ...

    async def fail(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        *,
        error: dict[str, Any],
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> AnalysisJobRecord: ...

    async def record_artifact(
        self,
        *,
        job_id: uuid.UUID,
        case_id: uuid.UUID,
        artifact_type: str,
        artifact_id: str,
        reference_uri: str,
        sha256: str,
        metadata: dict[str, Any] | None = None,
    ) -> AnalysisArtifact: ...


class PostgresAnalysisJobRepository:
    """Atomic queue operations built around row locks and worker leases."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def enqueue(
        self,
        *,
        case_id: uuid.UUID,
        tenant_id: str = "default",
        requested_by_user_id: uuid.UUID | None = None,
        workflow_version: str,
        idempotency_key: str,
        document_version_ids: list[str],
        document_hashes: list[str],
        enable_external_research: bool,
        max_attempts: int,
    ) -> EnqueueResult:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO analysis_jobs (
                        case_id,
                        tenant_id,
                        requested_by_user_id,
                        status,
                        workflow_version,
                        idempotency_key,
                        document_version_ids,
                        document_hashes,
                        enable_external_research,
                        max_attempts
                    )
                    VALUES ($1, $2, $3, 'queued', $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING *
                    """,
                    case_id,
                    tenant_id,
                    requested_by_user_id,
                    workflow_version,
                    idempotency_key,
                    document_version_ids,
                    document_hashes,
                    enable_external_research,
                    max_attempts,
                )
                created = row is not None
                if row is None:
                    row = await connection.fetchrow(
                        "SELECT * FROM analysis_jobs WHERE idempotency_key = $1",
                        idempotency_key,
                    )
                if row is None:
                    raise RuntimeError("Unable to create or recover analysis job")
                if created:
                    await self._append_event(
                        connection,
                        row["id"],
                        event_type="queued",
                        status=JobStatus.QUEUED,
                        message="Analysis job accepted and durably queued.",
                    )
                return EnqueueResult(
                    job=AnalysisJobRecord.from_row(row),
                    created=created,
                )

    async def get(self, job_id: uuid.UUID) -> AnalysisJobRecord | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM analysis_jobs WHERE id = $1",
                job_id,
            )
        return AnalysisJobRecord.from_row(row) if row else None

    async def list_case_jobs(
        self,
        case_id: uuid.UUID,
        *,
        tenant_id: str = "default",
        limit: int = 20,
    ) -> list[AnalysisJobRecord]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM analysis_jobs
                WHERE case_id = $1 AND tenant_id = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                case_id,
                tenant_id,
                limit,
            )
        return [AnalysisJobRecord.from_row(row) for row in rows]

    async def list_events(
        self,
        job_id: uuid.UUID,
        *,
        after_sequence: int = -1,
        limit: int = 100,
    ) -> list[AnalysisJobEvent]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM analysis_job_events
                WHERE job_id = $1 AND sequence > $2
                ORDER BY sequence
                LIMIT $3
                """,
                job_id,
                after_sequence,
                limit,
            )
        return [AnalysisJobEvent.from_row(row) for row in rows]

    async def claim_next(
        self,
        worker_id: str,
        lease_seconds: int,
    ) -> AnalysisJobRecord | None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                candidate = await connection.fetchrow(
                    """
                    SELECT id
                    FROM analysis_jobs
                    WHERE status = 'queued'
                      AND available_at <= NOW()
                      AND cancel_requested_at IS NULL
                      AND attempts < max_attempts
                    ORDER BY available_at, created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                )
                if candidate is None:
                    return None
                row = await connection.fetchrow(
                    """
                    UPDATE analysis_jobs
                    SET status = 'extracting',
                        attempts = attempts + 1,
                        worker_id = $2,
                        leased_until = NOW() + ($3 * INTERVAL '1 second'),
                        started_at = COALESCE(started_at, NOW()),
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING *
                    """,
                    candidate["id"],
                    worker_id,
                    lease_seconds,
                )
                await self._append_event(
                    connection,
                    candidate["id"],
                    event_type="claimed",
                    status=JobStatus.EXTRACTING,
                    agent="worker",
                    message=f"Worker {worker_id} leased the analysis job.",
                    payload={"attempt": row["attempts"]},
                )
                return AnalysisJobRecord.from_row(row)

    async def set_stage(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        status: JobStatus,
        *,
        agent: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> AnalysisJobRecord | None:
        if status not in ACTIVE_JOB_STATUSES:
            raise ValueError(f"{status.value} is not an active job stage")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE analysis_jobs
                    SET status = $3,
                        updated_at = NOW()
                    WHERE id = $1
                      AND worker_id = $2
                      AND status = ANY($4::text[])
                      AND cancel_requested_at IS NULL
                    RETURNING *
                    """,
                    job_id,
                    worker_id,
                    status.value,
                    [item.value for item in ACTIVE_JOB_STATUSES],
                )
                if row is None:
                    return None
                await self._append_event(
                    connection,
                    job_id,
                    event_type="stage",
                    status=status,
                    agent=agent,
                    message=message,
                    payload=payload,
                )
                return AnalysisJobRecord.from_row(row)

    async def heartbeat(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        lease_seconds: int,
    ) -> bool:
        async with self.pool.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE analysis_jobs
                SET leased_until = NOW() + ($3 * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE id = $1
                  AND worker_id = $2
                  AND status = ANY($4::text[])
                """,
                job_id,
                worker_id,
                lease_seconds,
                [item.value for item in ACTIVE_JOB_STATUSES],
            )
        return result == "UPDATE 1"

    async def is_cancel_requested(self, job_id: uuid.UUID) -> bool:
        async with self.pool.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT cancel_requested_at IS NOT NULL OR status = 'cancelled'
                FROM analysis_jobs
                WHERE id = $1
                """,
                job_id,
            )
        return bool(value)

    async def request_cancel(self, job_id: uuid.UUID) -> AnalysisJobRecord | None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    "SELECT * FROM analysis_jobs WHERE id = $1 FOR UPDATE",
                    job_id,
                )
                if row is None:
                    return None
                status = JobStatus(row["status"])
                if status in TERMINAL_JOB_STATUSES:
                    return AnalysisJobRecord.from_row(row)
                if status == JobStatus.QUEUED:
                    row = await connection.fetchrow(
                        """
                        UPDATE analysis_jobs
                        SET status = 'cancelled',
                            cancel_requested_at = NOW(),
                            completed_at = NOW(),
                            updated_at = NOW()
                        WHERE id = $1
                        RETURNING *
                        """,
                        job_id,
                    )
                else:
                    row = await connection.fetchrow(
                        """
                        UPDATE analysis_jobs
                        SET cancel_requested_at = COALESCE(cancel_requested_at, NOW()),
                            updated_at = NOW()
                        WHERE id = $1
                        RETURNING *
                        """,
                        job_id,
                    )
                await self._append_event(
                    connection,
                    job_id,
                    event_type="cancel_requested",
                    status=JobStatus(row["status"]),
                    message="Cancellation was requested.",
                )
                return AnalysisJobRecord.from_row(row)

    async def mark_cancelled(
        self,
        job_id: uuid.UUID,
        worker_id: str,
    ) -> AnalysisJobRecord:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE analysis_jobs
                    SET status = 'cancelled',
                        worker_id = NULL,
                        leased_until = NULL,
                        cancel_requested_at = COALESCE(cancel_requested_at, NOW()),
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1 AND worker_id = $2
                    RETURNING *
                    """,
                    job_id,
                    worker_id,
                )
                if row is None:
                    raise JobConflict("Worker no longer owns the cancelled job")
                await self._append_event(
                    connection,
                    job_id,
                    event_type="cancelled",
                    status=JobStatus.CANCELLED,
                    message="Analysis stopped at a cooperative cancellation boundary.",
                )
                return AnalysisJobRecord.from_row(row)

    async def retry(self, job_id: uuid.UUID) -> AnalysisJobRecord | None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    "SELECT * FROM analysis_jobs WHERE id = $1 FOR UPDATE",
                    job_id,
                )
                if current is None:
                    return None
                status = JobStatus(current["status"])
                if status not in {
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                    JobStatus.NEEDS_REVIEW,
                }:
                    raise JobConflict(
                        f"Job in {status.value} state cannot be manually retried"
                    )
                row = await connection.fetchrow(
                    """
                    UPDATE analysis_jobs
                    SET status = 'queued',
                        attempts = 0,
                        available_at = NOW(),
                        leased_until = NULL,
                        worker_id = NULL,
                        cancel_requested_at = NULL,
                        run_id = NULL,
                        report_id = NULL,
                        error = NULL,
                        started_at = NULL,
                        completed_at = NULL,
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING *
                    """,
                    job_id,
                )
                await self._append_event(
                    connection,
                    job_id,
                    event_type="manual_retry",
                    status=JobStatus.QUEUED,
                    message="Job was manually returned to the durable queue.",
                )
                return AnalysisJobRecord.from_row(row)

    async def complete(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        *,
        status: JobStatus,
        run_id: str,
        report_id: str,
    ) -> AnalysisJobRecord:
        if status not in {JobStatus.COMPLETED, JobStatus.NEEDS_REVIEW}:
            raise ValueError("Completed jobs must finish as completed or needs_review")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE analysis_jobs
                    SET status = $3,
                        run_id = $4,
                        report_id = $5,
                        worker_id = NULL,
                        leased_until = NULL,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1
                      AND worker_id = $2
                      AND status = ANY($6::text[])
                    RETURNING *
                    """,
                    job_id,
                    worker_id,
                    status.value,
                    run_id,
                    report_id,
                    [item.value for item in ACTIVE_JOB_STATUSES],
                )
                if row is None:
                    raise JobConflict("Worker no longer owns the completed job")
                await self._append_event(
                    connection,
                    job_id,
                    event_type="completed",
                    status=status,
                    agent="Verifier / Mediator",
                    message=(
                        "Analysis completed with verified provenance."
                        if status == JobStatus.COMPLETED
                        else "Analysis completed with unresolved review items."
                    ),
                    payload={"run_id": run_id, "report_id": report_id},
                )
                return AnalysisJobRecord.from_row(row)

    async def fail(
        self,
        job_id: uuid.UUID,
        worker_id: str,
        *,
        error: dict[str, Any],
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> AnalysisJobRecord:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """
                    SELECT *
                    FROM analysis_jobs
                    WHERE id = $1 AND worker_id = $2
                    FOR UPDATE
                    """,
                    job_id,
                    worker_id,
                )
                if current is None:
                    raise JobConflict("Worker no longer owns the failed job")
                if current["cancel_requested_at"] is not None:
                    return await self._mark_cancelled_in_transaction(
                        connection,
                        current,
                    )
                attempts = int(current["attempts"])
                max_attempts = int(current["max_attempts"])
                if attempts < max_attempts:
                    delay_seconds = retry_delay_seconds(
                        attempts,
                        retry_base_seconds,
                        retry_max_seconds,
                    )
                    row = await connection.fetchrow(
                        """
                        UPDATE analysis_jobs
                        SET status = 'queued',
                            available_at = NOW() + ($2 * INTERVAL '1 second'),
                            leased_until = NULL,
                            worker_id = NULL,
                            error = $3,
                            updated_at = NOW()
                        WHERE id = $1
                        RETURNING *
                        """,
                        job_id,
                        delay_seconds,
                        error,
                    )
                    await self._append_event(
                        connection,
                        job_id,
                        event_type="retry_scheduled",
                        status=JobStatus.QUEUED,
                        message=f"Attempt {attempts} failed; retry scheduled in {delay_seconds} seconds.",
                        payload={"attempt": attempts, "delay_seconds": delay_seconds},
                    )
                else:
                    row = await connection.fetchrow(
                        """
                        UPDATE analysis_jobs
                        SET status = 'failed',
                            leased_until = NULL,
                            worker_id = NULL,
                            error = $2,
                            completed_at = NOW(),
                            updated_at = NOW()
                        WHERE id = $1
                        RETURNING *
                        """,
                        job_id,
                        error,
                    )
                    await self._append_event(
                        connection,
                        job_id,
                        event_type="failed",
                        status=JobStatus.FAILED,
                        message=f"Analysis failed after {attempts} attempts.",
                        payload={"attempts": attempts},
                    )
                return AnalysisJobRecord.from_row(row)

    async def recover_stale_jobs(self, limit: int = 100) -> list[AnalysisJobRecord]:
        recovered: list[AnalysisJobRecord] = []
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    SELECT *
                    FROM analysis_jobs
                    WHERE status = ANY($1::text[])
                      AND leased_until < NOW()
                    ORDER BY leased_until
                    FOR UPDATE SKIP LOCKED
                    LIMIT $2
                    """,
                    [item.value for item in ACTIVE_JOB_STATUSES],
                    limit,
                )
                for current in rows:
                    if current["cancel_requested_at"] is not None:
                        row = await self._mark_cancelled_in_transaction(
                            connection,
                            current,
                        )
                    elif current["attempts"] >= current["max_attempts"]:
                        row = await connection.fetchrow(
                            """
                            UPDATE analysis_jobs
                            SET status = 'failed',
                                worker_id = NULL,
                                leased_until = NULL,
                                completed_at = NOW(),
                                error = COALESCE(
                                    error,
                                    '{"type":"LeaseExpired","message":"Worker lease expired."}'::jsonb
                                ),
                                updated_at = NOW()
                            WHERE id = $1
                            RETURNING *
                            """,
                            current["id"],
                        )
                        await self._append_event(
                            connection,
                            current["id"],
                            event_type="lease_expired",
                            status=JobStatus.FAILED,
                            message="Expired worker lease exhausted the retry budget.",
                        )
                    else:
                        row = await connection.fetchrow(
                            """
                            UPDATE analysis_jobs
                            SET status = 'queued',
                                worker_id = NULL,
                                leased_until = NULL,
                                available_at = NOW(),
                                updated_at = NOW()
                            WHERE id = $1
                            RETURNING *
                            """,
                            current["id"],
                        )
                        await self._append_event(
                            connection,
                            current["id"],
                            event_type="lease_recovered",
                            status=JobStatus.QUEUED,
                            message="Expired worker lease was recovered and requeued.",
                        )
                    recovered.append(AnalysisJobRecord.from_row(row))
        return recovered

    async def record_artifact(
        self,
        *,
        job_id: uuid.UUID,
        case_id: uuid.UUID,
        artifact_type: str,
        artifact_id: str,
        reference_uri: str,
        sha256: str,
        metadata: dict[str, Any] | None = None,
    ) -> AnalysisArtifact:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO analysis_artifacts (
                    job_id,
                    case_id,
                    artifact_type,
                    artifact_id,
                    reference_uri,
                    sha256,
                    metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (job_id, artifact_type, artifact_id)
                DO UPDATE SET
                    reference_uri = EXCLUDED.reference_uri,
                    sha256 = EXCLUDED.sha256,
                    metadata = EXCLUDED.metadata
                RETURNING *
                """,
                job_id,
                case_id,
                artifact_type,
                artifact_id,
                reference_uri,
                sha256,
                metadata or {},
            )
        return AnalysisArtifact.from_row(row)

    async def _mark_cancelled_in_transaction(
        self,
        connection: asyncpg.Connection,
        current: asyncpg.Record,
    ) -> AnalysisJobRecord:
        row = await connection.fetchrow(
            """
            UPDATE analysis_jobs
            SET status = 'cancelled',
                worker_id = NULL,
                leased_until = NULL,
                cancel_requested_at = COALESCE(cancel_requested_at, NOW()),
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            current["id"],
        )
        await self._append_event(
            connection,
            current["id"],
            event_type="cancelled",
            status=JobStatus.CANCELLED,
            message="Analysis stopped after cancellation was requested.",
        )
        return AnalysisJobRecord.from_row(row)

    async def _append_event(
        self,
        connection: asyncpg.Connection,
        job_id: uuid.UUID,
        *,
        event_type: str,
        status: JobStatus,
        message: str,
        agent: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AnalysisJobEvent:
        sequence = await connection.fetchval(
            """
            SELECT COALESCE(MAX(sequence), -1) + 1
            FROM analysis_job_events
            WHERE job_id = $1
            """,
            job_id,
        )
        row = await connection.fetchrow(
            """
            INSERT INTO analysis_job_events (
                job_id,
                sequence,
                event_type,
                status,
                agent,
                message,
                payload
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            job_id,
            sequence,
            event_type,
            status.value,
            agent,
            message,
            payload or {},
        )
        return AnalysisJobEvent.from_row(row)
