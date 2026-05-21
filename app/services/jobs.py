from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.collaboration import JobRecord
from app.core.enums import JobStatus
from app.repositories.collaboration import JobRepository


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = JobRepository(session)
        self.settings = get_settings()

    async def create(
        self,
        tenant_id: UUID,
        brand_space_id: UUID | None,
        job_type: str,
        payload: dict,
        knowledge_asset_id: UUID | None = None,
        content_version_id: UUID | None = None,
    ) -> JobRecord:
        job = JobRecord(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            job_type=job_type,
            status="queued",
            payload=payload,
            knowledge_asset_id=knowledge_asset_id,
            content_version_id=content_version_id,
            result_payload={},
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            started_at=None,
            finished_at=None,
        )
        await self.jobs.add(job)
        await self.session.commit()
        return job

    async def claim_pending(self, worker_id: str, limit: int | None = None) -> list[JobRecord]:
        now = datetime.now(timezone.utc)
        jobs = await self.jobs.claim_available(
            worker_id=worker_id,
            limit=limit or self.settings.worker_batch_size,
            now=now,
            lease_expires_at=now + timedelta(seconds=self.settings.worker_job_lease_seconds),
        )
        await self.session.commit()
        return jobs

    async def set_status(
        self,
        job_id: UUID,
        status: str,
        result_payload: dict | None = None,
        error_message: str | None = None,
        *,
        worker_id: str | None = None,
    ) -> JobRecord:
        job = await self.jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        if worker_id and job.lease_owner and job.lease_owner != worker_id:
            raise ValueError("Job is leased to a different worker")
        job.status = status
        if result_payload is not None:
            job.result_payload = result_payload
        if error_message is not None:
            job.error_message = error_message
        if status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            finished_at = datetime.now(timezone.utc)
            job.finished_at = finished_at
            job.lease_owner = None
            job.lease_expires_at = None
            job.heartbeat_at = finished_at
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def heartbeat(self, job_id: UUID, worker_id: str) -> JobRecord | None:
        job = await self.jobs.get(job_id)
        if not job or job.status != JobStatus.PROCESSING:
            return None
        if job.lease_owner and job.lease_owner != worker_id:
            return None
        now = datetime.now(timezone.utc)
        job.lease_owner = worker_id
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self.settings.worker_job_lease_seconds)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def list_for_tenant(self, tenant_id: UUID) -> list[JobRecord]:
        return await self.jobs.list_by_tenant(tenant_id)

    async def get(self, job_id: UUID) -> JobRecord | None:
        return await self.jobs.get(job_id)

    async def get_scoped(self, job_id: UUID, tenant_id: UUID) -> JobRecord | None:
        return await self.jobs.get_scoped(job_id, tenant_id)

    async def fail_or_retry(self, job_id: UUID, error_message: str, *, worker_id: str | None = None) -> JobRecord:
        job = await self.jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        if worker_id and job.lease_owner and job.lease_owner != worker_id:
            raise ValueError("Job is leased to a different worker")
        job.retry_count += 1
        job.error_message = error_message
        job.status = JobStatus.QUEUED if job.retry_count < job.max_retries else JobStatus.FAILED
        now = datetime.now(timezone.utc)
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = now
        if job.status == JobStatus.FAILED:
            job.finished_at = now
        else:
            job.finished_at = None
        await self.session.commit()
        await self.session.refresh(job)
        return job
