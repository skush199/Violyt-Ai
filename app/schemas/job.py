from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import APIModel


class JobResponse(APIModel):
    id: UUID
    tenant_id: UUID
    brand_space_id: UUID | None = None
    job_type: str
    status: str
    payload: dict
    result_payload: dict
    error_message: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
