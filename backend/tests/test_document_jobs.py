from __future__ import annotations

import io
import inspect
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.document_intelligence as document_api
from app.document_intelligence.ingestion import DocumentIngestionService
from app.document_intelligence.jobs import (
    AnalysisArtifact,
    AnalysisJobRecord,
    EnqueueResult,
    JobStatus,
    PostgresAnalysisJobRepository,
    build_analysis_idempotency_key,
    retry_delay_seconds,
)
from app.document_intelligence.models import utc_now
from app.document_intelligence.security import (
    DocumentPrincipal,
    RateLimitDecision,
    require_document_principal,
)
from app.document_intelligence.storage import LocalDocumentStore
from app.document_intelligence.worker import DurableAnalysisWorker
from app.document_intelligence.workflow import DocumentAnalysisWorkflow
from app.main import app


def make_job(
    case_id: uuid.UUID,
    version_ids: list[str],
    *,
    max_attempts: int = 3,
) -> AnalysisJobRecord:
    now = utc_now()
    return AnalysisJobRecord(
        id=uuid.uuid4(),
        case_id=case_id,
        status=JobStatus.QUEUED,
        workflow_version="track-c-1.1.0",
        idempotency_key="a" * 64,
        document_version_ids=version_ids,
        document_hashes=["b" * 64 for _ in version_ids],
        attempts=0,
        max_attempts=max_attempts,
        available_at=now,
        created_at=now,
        updated_at=now,
    )


class FakeJobRepository:
    def __init__(
        self,
        job: AnalysisJobRecord,
        *,
        cancel_at: JobStatus | None = None,
    ):
        self.job = job
        self.cancel_at = cancel_at
        self.events: list[tuple[str, JobStatus]] = []
        self.artifacts: list[AnalysisArtifact] = []
        self.retry_delays: list[int] = []

    async def recover_stale_jobs(self, limit: int = 100):
        return []

    async def claim_next(self, worker_id: str, lease_seconds: int):
        if self.job.status != JobStatus.QUEUED:
            return None
        now = utc_now()
        self.job = self.job.model_copy(
            update={
                "status": JobStatus.EXTRACTING,
                "attempts": self.job.attempts + 1,
                "worker_id": worker_id,
                "leased_until": now + timedelta(seconds=lease_seconds),
                "started_at": now,
                "updated_at": now,
            }
        )
        self.events.append(("claimed", JobStatus.EXTRACTING))
        return self.job

    async def set_stage(
        self,
        job_id,
        worker_id,
        status,
        *,
        agent,
        message,
        payload=None,
    ):
        assert job_id == self.job.id
        assert worker_id == self.job.worker_id
        if self.cancel_at == status:
            self.job = self.job.model_copy(
                update={"cancel_requested_at": utc_now()}
            )
            return None
        self.job = self.job.model_copy(
            update={"status": status, "updated_at": utc_now()}
        )
        self.events.append((agent, status))
        return self.job

    async def heartbeat(self, job_id, worker_id, lease_seconds):
        return (
            job_id == self.job.id
            and worker_id == self.job.worker_id
            and self.job.status
            not in {
                JobStatus.COMPLETED,
                JobStatus.NEEDS_REVIEW,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }
        )

    async def is_cancel_requested(self, job_id):
        assert job_id == self.job.id
        return self.job.cancel_requested_at is not None

    async def complete(
        self,
        job_id,
        worker_id,
        *,
        status,
        run_id,
        report_id,
    ):
        assert job_id == self.job.id
        assert worker_id == self.job.worker_id
        self.job = self.job.model_copy(
            update={
                "status": status,
                "worker_id": None,
                "leased_until": None,
                "run_id": run_id,
                "report_id": report_id,
                "completed_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self.events.append(("completed", status))
        return self.job

    async def mark_cancelled(self, job_id, worker_id):
        assert job_id == self.job.id
        assert worker_id == self.job.worker_id
        self.job = self.job.model_copy(
            update={
                "status": JobStatus.CANCELLED,
                "worker_id": None,
                "leased_until": None,
                "completed_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self.events.append(("cancelled", JobStatus.CANCELLED))
        return self.job

    async def fail(
        self,
        job_id,
        worker_id,
        *,
        error,
        retry_base_seconds,
        retry_max_seconds,
    ):
        assert job_id == self.job.id
        assert worker_id == self.job.worker_id
        if self.job.attempts < self.job.max_attempts:
            delay = retry_delay_seconds(
                self.job.attempts,
                retry_base_seconds,
                retry_max_seconds,
            )
            self.retry_delays.append(delay)
            self.job = self.job.model_copy(
                update={
                    "status": JobStatus.QUEUED,
                    "worker_id": None,
                    "leased_until": None,
                    "available_at": utc_now() + timedelta(seconds=delay),
                    "error": error,
                    "updated_at": utc_now(),
                }
            )
        else:
            self.job = self.job.model_copy(
                update={
                    "status": JobStatus.FAILED,
                    "worker_id": None,
                    "leased_until": None,
                    "error": error,
                    "completed_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
        return self.job

    async def record_artifact(
        self,
        *,
        job_id,
        case_id,
        artifact_type,
        artifact_id,
        reference_uri,
        sha256,
        metadata=None,
    ):
        artifact = AnalysisArtifact(
            id=uuid.uuid4(),
            job_id=job_id,
            case_id=case_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            reference_uri=reference_uri,
            sha256=sha256,
            metadata=metadata or {},
            created_at=utc_now(),
        )
        self.artifacts.append(artifact)
        return artifact


def ingest_job_document(
    store: LocalDocumentStore,
    case_id: uuid.UUID,
    tenant_id: str = "default",
):
    return DocumentIngestionService(store).ingest(
        tenant_id=tenant_id,
        case_id=str(case_id),
        filename="case.txt",
        media_type="text/plain",
        stream=io.BytesIO(
            """Petitioner: Asha Devi
FIR No. 42 of 2025 on 12/03/2025.
The complaint cites Section 154 of the Code.""".encode("utf-8")
        ),
        language_hint="en",
    ).document


def test_analysis_idempotency_uses_case_workflow_and_document_hashes():
    first = build_analysis_idempotency_key(
        case_id="case-1",
        workflow_version="track-c-1.1.0",
        document_versions=[("v2", "b" * 64), ("v1", "a" * 64)],
        enable_external_research=False,
    )
    reordered = build_analysis_idempotency_key(
        case_id="case-1",
        workflow_version="track-c-1.1.0",
        document_versions=[("v1", "a" * 64), ("v2", "b" * 64)],
        enable_external_research=False,
    )
    changed_hash = build_analysis_idempotency_key(
        case_id="case-1",
        workflow_version="track-c-1.1.0",
        document_versions=[("v1", "c" * 64), ("v2", "b" * 64)],
        enable_external_research=False,
    )

    changed_tenant = build_analysis_idempotency_key(
        case_id="case-1",
        tenant_id="tenant-b",
        workflow_version="track-c-1.1.0",
        document_versions=[("v2", "b" * 64), ("v1", "a" * 64)],
        enable_external_research=False,
    )

    assert first == reordered
    assert first != changed_hash
    assert first != changed_tenant
    assert len(first) == 64


def test_retry_backoff_is_exponential_and_capped():
    assert retry_delay_seconds(1, 15, 300) == 15
    assert retry_delay_seconds(2, 15, 300) == 30
    assert retry_delay_seconds(5, 15, 300) == 240
    assert retry_delay_seconds(6, 15, 300) == 300
    assert retry_delay_seconds(20, 15, 300) == 300


@pytest.mark.asyncio
async def test_worker_runs_all_stages_and_records_artifacts(tmp_path):
    case_id = uuid.uuid4()
    store = LocalDocumentStore(tmp_path)
    document = ingest_job_document(store, case_id, tenant_id="tenant-a")
    repository = FakeJobRepository(
        make_job(case_id, [document.version_id]).model_copy(
            update={"tenant_id": "tenant-a"}
        )
    )
    worker = DurableAnalysisWorker(
        repository,
        DocumentAnalysisWorkflow(store),
        worker_id="test-worker",
        heartbeat_seconds=60,
        poll_seconds=0,
    )

    assert await worker.run_once() is True

    assert repository.job.status in {
        JobStatus.COMPLETED,
        JobStatus.NEEDS_REVIEW,
    }
    stage_statuses = [status for _, status in repository.events]
    assert JobStatus.EXTRACTING in stage_statuses
    assert JobStatus.RESEARCHING in stage_statuses
    assert JobStatus.SYNTHESIZING in stage_statuses
    assert JobStatus.VERIFYING in stage_statuses
    assert {
        artifact.artifact_type for artifact in repository.artifacts
    } == {"run", "report", "evidence", "integrity", "research"}
    assert all(len(artifact.sha256) == 64 for artifact in repository.artifacts)


@pytest.mark.asyncio
async def test_worker_honours_cancellation_between_stages(tmp_path):
    case_id = uuid.uuid4()
    store = LocalDocumentStore(tmp_path)
    document = ingest_job_document(store, case_id)
    repository = FakeJobRepository(
        make_job(case_id, [document.version_id]),
        cancel_at=JobStatus.RESEARCHING,
    )
    worker = DurableAnalysisWorker(
        repository,
        DocumentAnalysisWorkflow(store),
        worker_id="test-worker",
        heartbeat_seconds=60,
    )

    assert await worker.run_once() is True
    assert repository.job.status == JobStatus.CANCELLED
    assert repository.artifacts == []


@pytest.mark.asyncio
async def test_worker_retries_then_exhausts_attempt_budget():
    case_id = uuid.uuid4()
    repository = FakeJobRepository(
        make_job(case_id, ["version-1"], max_attempts=2)
    )

    class FailingWorkflow:
        def run(self, *_args, **_kwargs):
            raise RuntimeError("transient parser failure")

    worker = DurableAnalysisWorker(
        repository,
        FailingWorkflow(),
        worker_id="test-worker",
        heartbeat_seconds=60,
        retry_base_seconds=10,
        retry_max_seconds=60,
    )

    assert await worker.run_once() is True
    assert repository.job.status == JobStatus.QUEUED
    assert repository.retry_delays == [10]

    repository.job = repository.job.model_copy(
        update={"available_at": utc_now()}
    )
    assert await worker.run_once() is True
    assert repository.job.status == JobStatus.FAILED
    assert repository.job.attempts == 2
    assert repository.job.error["type"] == "RuntimeError"


def test_postgres_claim_uses_skip_locked_and_schema_has_durable_tables():
    source = inspect.getsource(PostgresAnalysisJobRepository.claim_next)
    assert "FOR UPDATE SKIP LOCKED" in source

    schema = (
        Path(__file__).parents[1]
        / "data"
        / "document_intelligence_schema.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS analysis_jobs" in schema
    assert "CREATE TABLE IF NOT EXISTS analysis_job_events" in schema
    assert "CREATE TABLE IF NOT EXISTS analysis_artifacts" in schema


def test_document_analysis_routes_are_queue_based():
    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert (
        "/api/case-files/{case_id}/analysis-jobs",
        "POST",
    ) in routes
    assert ("/api/analysis-jobs/{job_id}", "GET") in routes
    assert ("/api/analysis-jobs/{job_id}/events", "GET") in routes
    assert ("/api/analysis-jobs/{job_id}/cancel", "POST") in routes
    assert ("/api/analysis-jobs/{job_id}/retry", "POST") in routes
@pytest.mark.asyncio
async def test_enqueue_api_returns_202_and_deduplicates(monkeypatch, tmp_path):
    case_id = uuid.uuid4()
    store = LocalDocumentStore(tmp_path)
    document = ingest_job_document(store, case_id)

    class FakeEnqueueRepository:
        def __init__(self):
            self.jobs = {}

        async def enqueue(self, **values):
            existing = self.jobs.get(values["idempotency_key"])
            if existing is not None:
                return EnqueueResult(job=existing, created=False)
            job = make_job(
                values["case_id"],
                values["document_version_ids"],
                max_attempts=values["max_attempts"],
            ).model_copy(
                update={
                    "idempotency_key": values["idempotency_key"],
                    "document_hashes": values["document_hashes"],
                    "enable_external_research": values[
                        "enable_external_research"
                    ],
                    "workflow_version": values["workflow_version"],
                }
            )
            self.jobs[values["idempotency_key"]] = job
            return EnqueueResult(job=job, created=True)

    repository = FakeEnqueueRepository()
    principal = DocumentPrincipal(
        user_id=uuid.uuid4(),
        tenant_id="default",
    )

    class FakeSecurityRepository:
        async def consume_rate_limit(self, *_args, limit, **_kwargs):
            return RateLimitDecision(True, limit, limit - 1, 1)

        async def case_is_owned(self, requested_case_id, requested_principal):
            return requested_case_id == case_id and requested_principal == principal

        async def write_audit(self, _event):
            pass

    security_repository = FakeSecurityRepository()

    async def fake_repository():
        return repository

    async def fake_security_repository():
        return security_repository

    monkeypatch.setattr(document_api, "_store", store)
    monkeypatch.setattr(document_api, "_job_repository", fake_repository)
    monkeypatch.setattr(
        document_api,
        "_security_repository",
        fake_security_repository,
    )
    app.dependency_overrides[require_document_principal] = lambda: principal

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            first = await client.post(
                f"/api/case-files/{case_id}/analysis-jobs",
                json={
                    "document_version_ids": [document.version_id],
                    "enable_external_research": True,
                },
            )
            second = await client.post(
                f"/api/case-files/{case_id}/analysis-jobs",
                json={
                    "document_version_ids": [document.version_id],
                    "enable_external_research": True,
                },
            )
    finally:
        app.dependency_overrides.pop(require_document_principal, None)

    assert first.status_code == 202
    assert first.json()["status"] == "queued"
    assert first.json()["deduplicated"] is False
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["deduplicated"] is True
