from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UsageMetricCode
from app.core.exceptions import UsageLimitExceededError
from app.models.collaboration import UsageConsumption
from app.repositories.collaboration import UsageConsumptionRepository, UsageLimitRepository
from app.utils.text import current_period_key


class UsageLimitService:
    FIELD_MAP = {
        UsageMetricCode.USERS: "max_users",
        UsageMetricCode.BRAND_SPACES: "max_brand_spaces",
        UsageMetricCode.CONTENT_GENERATIONS: "max_content_generations",
        UsageMetricCode.IMAGE_GENERATIONS: "max_image_generations",
        UsageMetricCode.OCR_PAGES: "max_ocr_pages",
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.limits = UsageLimitRepository(session)
        self.consumption = UsageConsumptionRepository(session)

    async def enforce(self, tenant_id: UUID, metric_code: str, amount: int = 1) -> None:
        usage_limit = await self.limits.get_by_tenant(tenant_id)
        if not usage_limit:
            return
        limit_field = self.FIELD_MAP[metric_code]
        limit_value = getattr(usage_limit, limit_field)
        period_key = current_period_key()
        consumption = await self.consumption.get_metric(tenant_id, metric_code, period_key)
        current_value = consumption.consumed if consumption else 0
        if current_value + amount > limit_value:
            raise UsageLimitExceededError(f"Usage limit exceeded for {metric_code}")

    async def increment(self, tenant_id: UUID, metric_code: str, amount: int = 1) -> None:
        period_key = current_period_key()
        metric = await self.consumption.get_metric(tenant_id, metric_code, period_key)
        if not metric:
            metric = UsageConsumption(
                tenant_id=tenant_id,
                metric_code=metric_code,
                period_key=period_key,
                consumed=0,
                metadata_json={},
            )
            await self.consumption.add(metric)
        metric.consumed += amount
        await self.session.flush()

    async def decrement(self, tenant_id: UUID, metric_code: str, amount: int = 1) -> None:
        period_key = current_period_key()
        metric = await self.consumption.get_metric(tenant_id, metric_code, period_key)
        if not metric:
            return
        metric.consumed = max(0, int(metric.consumed or 0) - max(0, int(amount or 0)))
        await self.session.flush()

    async def summary(self, tenant_id: UUID) -> dict[str, int]:
        period_key = current_period_key()
        values: dict[str, int] = {}
        for metric_code in self.FIELD_MAP:
            metric = await self.consumption.get_metric(tenant_id, metric_code, period_key)
            values[metric_code] = metric.consumed if metric else 0
        return values

