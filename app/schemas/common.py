from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.studio import resolve_studio_panel_defaults


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(APIModel):
    message: str


class PaginatedResponse(APIModel):
    items: list[Any]
    total: int


class AuditMetadata(APIModel):
    created_at: datetime
    updated_at: datetime


class StudioPanelSelection(APIModel):
    format: str
    platform_preset: str
    file_type: str
    size: dict[str, int] | None = None
    pinned_template_id: UUID | None = None

    @model_validator(mode="after")
    def apply_defaults(self) -> "StudioPanelSelection":
        resolved = resolve_studio_panel_defaults(self.model_dump())
        self.format = resolved["format"]
        self.platform_preset = resolved["platform_preset"]
        self.file_type = resolved["file_type"]
        self.size = resolved["size"]
        return self


class AssetReference(APIModel):
    asset_id: UUID
    mime_type: str
    storage_path: str
    asset_url: str | None = None
    width: int | None = None
    height: int | None = None
    asset_role: str
