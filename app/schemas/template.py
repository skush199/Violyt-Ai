from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class TemplateUploadRequest(APIModel):
    name: str
    description: str | None = None
    kind: str = "hybrid"
    filename: str
    mime_type: str
    content_base64: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class TemplateMetadataUpsertRequest(APIModel):
    zone_map: dict = Field(default_factory=dict)
    sizing_rules: dict = Field(default_factory=dict)
    platform_rules: dict = Field(default_factory=dict)
    editable_fields: list[str] = Field(default_factory=list)
    export_rules: dict = Field(default_factory=dict)


class TemplateApplyRequest(APIModel):
    template_id: UUID
    prompt: str = Field(min_length=1)
    studio_panel: dict


class TemplateRecommendRequest(APIModel):
    prompt: str = Field(min_length=1)
    studio_panel: dict
    limit: int = Field(default=5, ge=1, le=20)


class TemplateRecommendationResponse(APIModel):
    template_id: UUID
    name: str
    display_name: str | None = None
    asset_url: str | None = None
    score: float
    match_type: str = "adapted_template"
    decision_confidence: float | None = None
    format_family: str | None = None
    is_primary_adaptation: bool = False
    selection_reason: str | None = None
    recommendation_group_key: str | None = None
    reasons: list[str] = Field(default_factory=list)
    score_breakdown: dict = Field(default_factory=dict)
    adaptation_plan: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class TemplateResponse(APIModel):
    id: UUID
    name: str
    description: str | None = None
    kind: str
    storage_path: str
    asset_url: str | None = None
    source_knowledge_asset_id: UUID | None = None
    origin_field_key: str | None = None
    tags: list[str]
    analysis_json: dict
    matcher_features_json: dict = Field(default_factory=dict)
