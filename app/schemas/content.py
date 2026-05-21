from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import APIModel, AssetReference, StudioPanelSelection


class RequestInheritancePolicy(APIModel):
    inherit_persona: bool | None = None
    inherit_objective: bool | None = None
    inherit_template: bool | None = None
    inherit_reference_assets: bool | None = None
    inherit_copy_context: bool | None = None
    inherit_layout_context: bool | None = None


class ContentGenerateRequest(APIModel):
    prompt: str = Field(min_length=1)
    raw_user_prompt: str | None = None
    rewrite_instruction: str | None = None
    source_prompt_snapshot: str | None = None
    session_id: UUID | None = None
    persona_id: UUID | None = None
    objective_id: UUID | None = None
    template_id: UUID | None = None
    request_mode: str | None = None
    source_content_version_id: UUID | None = None
    inheritance_policy: RequestInheritancePolicy = Field(default_factory=RequestInheritancePolicy)
    studio_panel: StudioPanelSelection
    generate_image: bool = True
    reference_asset_ids: list[UUID] = Field(default_factory=list)


class ContentRewriteRequest(APIModel):
    content_version_id: UUID
    rewrite_instruction: str = Field(min_length=1)
    studio_panel: StudioPanelSelection
    revision_scope: dict[str, Any] | None = None


class ToneCheckRequest(APIModel):
    content: str | None = None
    persona_id: UUID | None = None
    objective_id: UUID | None = None
    content_version_id: UUID | None = None
    content_payload: dict[str, Any] | None = None
    message_strategy: dict[str, Any] | None = None
    objective_context: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_inputs(self) -> "ToneCheckRequest":
        self.content = str(self.content or "").strip() or None
        if not self.content and not self.content_version_id and not self.content_payload:
            raise ValueError("Provide content, content_payload, or content_version_id for tone evaluation.")
        return self


class ContentExportRequest(APIModel):
    content_version_id: UUID
    export_format: str
    studio_panel: dict[str, Any] | None = None
    blueprint_payload: dict[str, Any] | None = None
    template_id: UUID | None = None


class ContentCopyRequest(APIModel):
    content_version_id: UUID


class ToneEvaluationResponse(APIModel):
    score: int
    matched_signals: list[str]
    deviations: list[str]
    rewrite_suggestions: list[str]
    quality_summary: list[str] = Field(default_factory=list)
    persuasion_dimensions: dict[str, int] = Field(default_factory=dict)
    field_guidance: dict[str, list[str]] = Field(default_factory=dict)


class ContentVersionResponse(APIModel):
    id: UUID
    session_id: UUID
    parent_version_id: UUID | None = None
    lifecycle_state: str
    content_type: str
    title: str | None = None
    prompt: str
    studio_panel: dict[str, Any]
    generated_payload: dict[str, Any]
    blueprint_payload: dict[str, Any]
    explainability_metadata: dict[str, Any]
    generation_decision: dict[str, Any] = Field(default_factory=dict)
    scene_graph: dict[str, Any] = Field(default_factory=dict)
    creative_decision: dict[str, Any] = Field(default_factory=dict)
    validation_report: dict[str, Any] = Field(default_factory=dict)
    repair_attempts: int = 0
    tone_score: int | None = None
    tone_feedback: dict[str, Any] = Field(default_factory=dict)
    assets: list[AssetReference] = Field(default_factory=list)
