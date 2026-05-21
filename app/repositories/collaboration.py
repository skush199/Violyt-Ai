from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import (
    AnalyticsSnapshot,
    JobRecord,
    ReviewComment,
    ReviewLink,
    SocialConnection,
    UsageConsumption,
    UsageLimit,
)
from app.repositories.base import Repository


class ReviewLinkRepository(Repository[ReviewLink]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ReviewLink)

    async def get_by_token(self, token: str) -> ReviewLink | None:
        result = await self.session.execute(select(ReviewLink).where(ReviewLink.token == token))
        return result.scalar_one_or_none()


class ReviewCommentRepository(Repository[ReviewComment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ReviewComment)

    async def list_for_link(self, review_link_id: UUID) -> list[ReviewComment]:
        result = await self.session.execute(select(ReviewComment).where(ReviewComment.review_link_id == review_link_id))
        return list(result.scalars().all())


class SocialConnectionRepository(Repository[SocialConnection]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SocialConnection)

    async def get_by_platform(self, brand_space_id: UUID, platform: str) -> SocialConnection | None:
        result = await self.session.execute(
            select(SocialConnection).where(
                SocialConnection.brand_space_id == brand_space_id,
                SocialConnection.platform == platform,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_brand(self, tenant_id: UUID, brand_space_id: UUID) -> list[SocialConnection]:
        result = await self.session.execute(
            select(SocialConnection).where(
                SocialConnection.tenant_id == tenant_id,
                SocialConnection.brand_space_id == brand_space_id,
            )
        )
        return list(result.scalars().all())


class AnalyticsRepository(Repository[AnalyticsSnapshot]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AnalyticsSnapshot)

    async def list_by_scope(self, tenant_id: UUID, brand_space_id: UUID | None = None) -> list[AnalyticsSnapshot]:
        stmt = select(AnalyticsSnapshot).where(AnalyticsSnapshot.tenant_id == tenant_id)
        if brand_space_id:
            stmt = stmt.where(AnalyticsSnapshot.brand_space_id == brand_space_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class UsageLimitRepository(Repository[UsageLimit]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UsageLimit)

    async def get_by_tenant(self, tenant_id: UUID) -> UsageLimit | None:
        result = await self.session.execute(select(UsageLimit).where(UsageLimit.tenant_id == tenant_id))
        return result.scalar_one_or_none()


class UsageConsumptionRepository(Repository[UsageConsumption]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UsageConsumption)

    async def get_metric(self, tenant_id: UUID, metric_code: str, period_key: str) -> UsageConsumption | None:
        result = await self.session.execute(
            select(UsageConsumption).where(
                UsageConsumption.tenant_id == tenant_id,
                UsageConsumption.metric_code == metric_code,
                UsageConsumption.period_key == period_key,
            )
        )
        return result.scalar_one_or_none()


class JobRepository(Repository[JobRecord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, JobRecord)

    async def list_by_tenant(self, tenant_id: UUID) -> list[JobRecord]:
        result = await self.session.execute(select(JobRecord).where(JobRecord.tenant_id == tenant_id))
        return list(result.scalars().all())

    async def get_scoped(self, job_id: UUID, tenant_id: UUID) -> JobRecord | None:
        result = await self.session.execute(
            select(JobRecord).where(
                JobRecord.id == job_id,
                JobRecord.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_pending(self, limit: int) -> list[JobRecord]:
        result = await self.session.execute(
            select(JobRecord)
            .where(JobRecord.status.in_(["queued", "processing"]))
            .order_by(JobRecord.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def claim_available(
        self,
        *,
        worker_id: str,
        limit: int,
        now: datetime,
        lease_expires_at: datetime,
    ) -> list[JobRecord]:
        result = await self.session.execute(
            select(JobRecord)
            .where(
                or_(
                    JobRecord.status == "queued",
                    and_(
                        JobRecord.status == "processing",
                        or_(
                            JobRecord.lease_expires_at.is_(None),
                            JobRecord.lease_expires_at < now,
                        ),
                    ),
                )
            )
            .order_by(JobRecord.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = list(result.scalars().all())
        for job in jobs:
            job.status = "processing"
            job.lease_owner = worker_id
            job.lease_expires_at = lease_expires_at
            job.heartbeat_at = now
            job.started_at = job.started_at or now
            job.finished_at = None
        await self.session.flush()
        return jobs
