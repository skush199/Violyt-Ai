from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, AssetReference


class RenderLayoutRequest(APIModel):
    content_version_id: UUID
    blueprint_payload: dict | None = None
    studio_panel: dict
    template_id: UUID | None = None


class RenderPreviewRequest(APIModel):
    content_version_id: UUID
    blueprint_payload: dict | None = None
    studio_panel: dict
    template_id: UUID | None = None


class RenderExportRequest(APIModel):
    content_version_id: UUID
    studio_panel: dict
    export_format: str
    blueprint_payload: dict | None = None
    template_id: UUID | None = None


class RenderResponse(APIModel):
    content_version_id: UUID
    preview_asset: AssetReference | None = None
    export_assets: list[AssetReference] = Field(default_factory=list)
    renderer_metadata: dict
