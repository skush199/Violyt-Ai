from __future__ import annotations

import asyncio
from contextlib import suppress
import os
from pathlib import Path
import socket
from uuid import uuid4

from app.core.config import get_settings
from app.core.enums import JobStatus, JobType
from app.db.session import AsyncSessionLocal
from app.repositories.collaboration import JobRepository
from app.services.jobs import JobService
from app.services.knowledge import KnowledgeService
from app.services.template import TemplateService


def _build_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


def _run_ragas_evaluation(trace_id: str) -> dict[str, str]:
    from scripts.ragas_evaluation import evaluate_traces

    settings = get_settings()
    trace_root = Path(settings.generation_trace_base_path)
    output_root = Path(settings.object_storage_base_path) / "ragas_evaluation"
    result = evaluate_traces(trace_root, output_root, trace_id)
    output_dir = output_root / trace_id
    return {
        "trace_id": trace_id,
        "output_dir": str(output_dir),
        "output": str(output_dir / "ragas_evaluation.json"),
        "evaluator": str(result.get("evaluator") or ""),
    }


async def _heartbeat_loop(job_id, worker_id: str, stop: asyncio.Event) -> None:
    settings = get_settings()
    while not stop.is_set():
        await asyncio.sleep(settings.worker_job_heartbeat_seconds)
        if stop.is_set():
            return
        async with AsyncSessionLocal() as session:
            await JobService(session).heartbeat(job_id, worker_id)


async def handle_job(job_id, worker_id: str):
    stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat_loop(job_id, worker_id, stop))
    async with AsyncSessionLocal() as session:
        jobs = JobService(session)
        repo = JobRepository(session)
        job = await repo.get(job_id)
        if not job or job.status != JobStatus.PROCESSING:
            stop.set()
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            return
        try:
            if job.job_type == JobType.KNOWLEDGE_PROCESS and job.knowledge_asset_id:
                asset = await KnowledgeService(session).process_asset(job.knowledge_asset_id)
                await jobs.set_status(
                    job.id,
                    JobStatus.SUCCEEDED,
                    {"knowledge_asset_id": str(asset.id)},
                    worker_id=worker_id,
                )
            elif job.job_type == JobType.TEMPLATE_ANALYSIS:
                template = await TemplateService(session).analyze(job.payload["template_id"])
                await jobs.set_status(
                    job.id,
                    JobStatus.SUCCEEDED,
                    {"template_id": str(template.id)},
                    worker_id=worker_id,
                )
            elif job.job_type == JobType.RAGAS_EVALUATION:
                trace_id = str((job.payload or {}).get("trace_id") or "").strip()
                if not trace_id:
                    raise ValueError("RAGAS evaluation job missing trace_id")
                result = await asyncio.to_thread(_run_ragas_evaluation, trace_id)
                await jobs.set_status(
                    job.id,
                    JobStatus.SUCCEEDED,
                    result,
                    worker_id=worker_id,
                )
            else:
                await jobs.set_status(
                    job.id,
                    JobStatus.SUCCEEDED,
                    {"message": "No-op job completed"},
                    worker_id=worker_id,
                )
        except Exception as exc:  # noqa: BLE001
            await jobs.fail_or_retry(job.id, str(exc), worker_id=worker_id)
        finally:
            stop.set()
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task


async def run_worker_loop() -> None:
    settings = get_settings()
    worker_id = _build_worker_id()
    while True:
        async with AsyncSessionLocal() as session:
            pending = await JobService(session).claim_pending(worker_id, settings.worker_batch_size)
        for job in pending:
            await handle_job(job.id, worker_id)
        await asyncio.sleep(settings.worker_poll_interval_seconds)
