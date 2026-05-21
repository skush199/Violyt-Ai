from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class KnowledgeUploadRequest(APIModel):
    name: str
    filename: str
    mime_type: str
    content_base64: str = Field(min_length=1)
    channel: str = "brand"
    metadata: dict = Field(default_factory=dict)
    skip_processing: bool = False


class KnowledgeAssetResponse(APIModel):
    id: UUID
    brand_space_id: UUID | None = None
    name: str
    original_filename: str
    mime_type: str
    storage_path: str
    asset_url: str | None = None
    lifecycle_state: str
    channel: str
    field_key: str | None = None
    asset_category: str | None = None
    page_count: int
    metadata_json: dict
    structured_data_json: dict = Field(default_factory=dict)
    normalized_data_json: dict = Field(default_factory=dict)
    validation_state: str = "pending"
    validation_summary_json: dict = Field(default_factory=dict)
    is_active: bool = True
    processing_error: str | None = None


class KnowledgeReprocessRequest(APIModel):
    channel: str | None = None
