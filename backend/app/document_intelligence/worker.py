"""Standalone durable worker for Track C document-analysis jobs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import signal
import socket
import threading
import uuid
from time import monotonic
from typing import Any

from app.config import settings
from app.db.neon_client import close_pool, get_pool
from app.document_intelligence.jobs import (
    AnalysisJobRecord,
    AnalysisJobRepositoryProtocol,
    JobConflict,
    JobStatus,
    PostgresAnalysisJobRepository,
)
from app.document_intelligence.models import AnalysisBundle, AnalysisStatus
from app.document_intelligence.storage import create_document_store
from app.document_intelligence.workflow import DocumentAnalysisWorkflow


logger = logging.getLogger(__name__)


class AnalysisJobCancelled(RuntimeError):
    pass


_JOB_STAGE_BY_ANALYSIS_STATUS = {
    AnalysisStatus.EXTRACTING: JobStatus.EXTRACTING,
    AnalysisStatus.RETRIEVING: JobStatus.RESEARCHING,
    AnalysisStatus.RELATING: JobStatus.SYNTHESIZING,
    AnalysisStatus.SYNTHESIZING: JobStatus.SYNTHESIZING,
    AnalysisStatus.CRITIQUING: JobStatus.VERIFYING,
    AnalysisStatus.VERIFYING: JobStatus.VERIFYING,
}


class DurableAnalysisWorker:
    """Claims leased PostgreSQL jobs and executes workflows outside the web app."""

    def __init__(
        self,
        repository: AnalysisJobRepositoryProtocol,
        workflow: DocumentAnalysisWorkflow,
        *,
        worker_id: str | None = None,
        lease_seconds: int | None = None,
        heartbeat_seconds: int | None = None,
        poll_seconds: float | None = None,
        retry_base_seconds: int | None = None,
        retry_max_seconds: int | None = None,
        stale_recovery_seconds: int | None = None,
    ):
        self.repository = repository
        self.workflow = workflow
        self.worker_id = worker_id or self._default_worker_id()
        self.lease_seconds = lease_seconds or settings.analysis_job_lease_seconds
        self.heartbeat_seconds = (
            heartbeat_seconds or settings.analysis_job_heartbeat_seconds
        )
        self.poll_seconds = (
            poll_seconds
            if poll_seconds is not None
            else settings.analysis_job_poll_seconds
        )
        self.retry_base_seconds = (
            retry_base_seconds or settings.analysis_job_retry_base_seconds
        )
        self.retry_max_seconds = (
            retry_max_seconds or settings.analysis_job_retry_max_seconds
        )
        self.stale_recovery_seconds = (
            stale_recovery_seconds
            or settings.analysis_job_stale_recovery_seconds
        )
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("Heartbeat interval must be shorter than the worker lease")

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        last_recovery = 0.0
        logger.info("[analysis-worker] started | worker=%s", self.worker_id)
        while not stop.is_set():
            now = monotonic()
            if now - last_recovery >= self.stale_recovery_seconds:
                recovered = await self.repository.recover_stale_jobs()
                if recovered:
                    logger.warning(
                        "[analysis-worker] recovered %d expired lease(s)",
                        len(recovered),
                    )
                last_recovery = now

            processed = await self.run_once(recover_stale=False)
            if processed:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass
        logger.info("[analysis-worker] stopped | worker=%s", self.worker_id)

    async def run_once(self, *, recover_stale: bool = True) -> bool:
        if recover_stale:
            await self.repository.recover_stale_jobs()
        job = await self.repository.claim_next(
            self.worker_id,
            self.lease_seconds,
        )
        if job is None:
            return False
        await self._process(job)
        return True

    async def _process(self, job: AnalysisJobRecord) -> None:
        loop = asyncio.get_running_loop()
        heartbeat_stop = asyncio.Event()
        lease_lost = threading.Event()
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(job.id, heartbeat_stop, lease_lost)
        )

        async def publish_progress(
            status: AnalysisStatus,
            agent: str,
            message: str,
        ) -> None:
            if lease_lost.is_set():
                raise JobConflict("Worker lease was lost")
            if await self.repository.is_cancel_requested(job.id):
                raise AnalysisJobCancelled("Cancellation requested")
            job_status = _JOB_STAGE_BY_ANALYSIS_STATUS[status]
            updated = await self.repository.set_stage(
                job.id,
                self.worker_id,
                job_status,
                agent=agent,
                message=message,
                payload={"analysis_status": status.value},
            )
            if updated is None:
                if await self.repository.is_cancel_requested(job.id):
                    raise AnalysisJobCancelled("Cancellation requested")
                raise JobConflict("Worker no longer owns the job")

        def progress_callback(
            status: AnalysisStatus,
            agent: str,
            message: str,
        ) -> None:
            future = asyncio.run_coroutine_threadsafe(
                publish_progress(status, agent, message),
                loop,
            )
            future.result(timeout=max(self.heartbeat_seconds, 30))

        try:
            bundle = await asyncio.to_thread(
                self.workflow.run,
                str(job.case_id),
                job.document_version_ids,
                None,
                job.enable_external_research,
                progress_callback,
                job.tenant_id,
            )
            if lease_lost.is_set():
                raise JobConflict("Worker lease was lost")
            if await self.repository.is_cancel_requested(job.id):
                raise AnalysisJobCancelled("Cancellation requested")

            await self._record_artifacts(job, bundle)
            final_status = (
                JobStatus.NEEDS_REVIEW
                if bundle.report.status == AnalysisStatus.NEEDS_REVIEW
                else JobStatus.COMPLETED
            )
            await self.repository.complete(
                job.id,
                self.worker_id,
                status=final_status,
                run_id=bundle.run.run_id,
                report_id=bundle.report.report_id,
            )
        except AnalysisJobCancelled:
            await self.repository.mark_cancelled(job.id, self.worker_id)
        except JobConflict as exc:
            logger.error(
                "[analysis-worker] ownership lost | job=%s worker=%s err=%s",
                job.id,
                self.worker_id,
                exc,
            )
        except Exception as exc:
            logger.exception(
                "[analysis-worker] execution failed | job=%s attempt=%d",
                job.id,
                job.attempts,
            )
            try:
                await self.repository.fail(
                    job.id,
                    self.worker_id,
                    error={
                        "type": type(exc).__name__,
                        "message": str(exc)[:2000],
                    },
                    retry_base_seconds=self.retry_base_seconds,
                    retry_max_seconds=self.retry_max_seconds,
                )
            except JobConflict:
                logger.error(
                    "[analysis-worker] could not persist failure after lease loss | job=%s",
                    job.id,
                )
        finally:
            heartbeat_stop.set()
            await heartbeat_task

    async def _heartbeat_loop(
        self,
        job_id: uuid.UUID,
        stop: asyncio.Event,
        lease_lost: threading.Event,
    ) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=self.heartbeat_seconds,
                )
                break
            except TimeoutError:
                try:
                    renewed = await self.repository.heartbeat(
                        job_id,
                        self.worker_id,
                        self.lease_seconds,
                    )
                except Exception:
                    logger.exception(
                        "[analysis-worker] heartbeat failed | job=%s",
                        job_id,
                    )
                    lease_lost.set()
                    return
                if not renewed:
                    lease_lost.set()
                    return

    async def _record_artifacts(
        self,
        job: AnalysisJobRecord,
        bundle: AnalysisBundle,
    ) -> None:
        artifacts: list[tuple[str, str, dict[str, Any]]] = [
            ("run", bundle.run.run_id, bundle.run.model_dump(mode="json")),
            (
                "report",
                bundle.report.report_id,
                bundle.report.model_dump(mode="json"),
            ),
            (
                "evidence",
                bundle.run.run_id,
                {
                    "items": [
                        item.model_dump(mode="json")
                        for item in bundle.evidence
                    ]
                },
            ),
            (
                "integrity",
                bundle.run.run_id,
                {
                    "result": bundle.integrity.model_dump(mode="json"),
                    "review_items": [
                        item.model_dump(mode="json")
                        for item in bundle.review_items
                    ],
                },
            ),
        ]
        if bundle.research is not None:
            artifacts.append(
                (
                    "research",
                    bundle.run.run_id,
                    bundle.research.model_dump(mode="json"),
                )
            )

        for artifact_type, artifact_id, payload in artifacts:
            encoded = json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            await self.repository.record_artifact(
                job_id=job.id,
                case_id=job.case_id,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                reference_uri=(
                    f"case-artifact://{job.case_id}/{artifact_type}/{artifact_id}"
                ),
                sha256=hashlib.sha256(encoded).hexdigest(),
                metadata={
                    "workflow_version": job.workflow_version,
                    "attempt": job.attempts,
                },
            )

    @staticmethod
    def _default_worker_id() -> str:
        return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


async def _run_worker() -> None:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the durable analysis worker")

    pool = await get_pool()
    repository = PostgresAnalysisJobRepository(pool)
    store = create_document_store(settings)
    worker = DurableAnalysisWorker(
        repository,
        DocumentAnalysisWorkflow(store),
    )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await worker.run_forever(stop_event)
    finally:
        await close_pool()


def main() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(_run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()