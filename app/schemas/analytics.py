from __future__ import annotations

from typing import Any
from uuid import UUID

from app.schemas.common import APIModel


class AnalyticsResponse(APIModel):
    scope: str
    tenant_id: UUID | None = None
    brand_space_id: UUID | None = None
    metrics: dict[str, Any]
