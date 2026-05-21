from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AIOrchestrationRequest(BaseModel):
    tenant_id: UUID
    brand_space_id: UUID
    user_id: UUID
    prompt: str
    studio_panel: dict[str, Any]
    conversation_context: dict[str, Any] = Field(default_factory=dict)
    session_memory: dict[str, Any] = Field(default_factory=dict)
    resolved_brand_context: dict[str, Any]
    persona_context: dict[str, Any]
    objective_context: dict[str, Any]
    retrieved_knowledge: dict[str, list[dict[str, Any]]]
    template_context: dict[str, Any] | None = None
    content_format_guide: dict[str, Any] = Field(default_factory=dict)
    live_research: dict[str, Any] = Field(default_factory=dict)
    research_editorial_brief: dict[str, Any] = Field(default_factory=dict)
    format_family_plan: dict[str, Any] = Field(default_factory=dict)
    content_plan: dict[str, Any] = Field(
        default_factory=dict,
        description="Compact execution plan for copy structure, pacing, and native metadata expectations.",
    )
    visual_plan: dict[str, Any] = Field(
        default_factory=dict,
        description="Compact execution plan for page/frame sequencing and visual rendering strategy.",
    )
    template_candidates: list[dict[str, Any]] = Field(default_factory=list)
    layout_decision: dict[str, Any] = Field(default_factory=dict)
    reference_assets: list[dict[str, Any]] = Field(default_factory=list)
    asset_catalog: list[dict[str, Any]] = Field(default_factory=list)
    logo_asset_path: str | None = None
    logo_asset_candidates: list[dict[str, Any]] = Field(default_factory=list)
    platform_constraints: dict[str, Any] = Field(default_factory=dict)
    resolution_policy: dict[str, Any] = Field(default_factory=dict)
    validation_report: dict[str, Any] | None = None
    generation_trace_id: str | None = None
    generate_image: bool = True
    input_access_tracker: Any | None = None


class StructuredTextPayload(BaseModel):
    headline: str
    body: str
    cta: str
    hashtags: list[str]
    metadata: dict[str, Any]


class MessageStrategyPayload(BaseModel):
    primary_campaign_theme: str = ""
    core_audience_message: str = ""
    headline_direction: str = ""
    supporting_copy_direction: str = ""
    cta_intent: str = ""
    key_value_proposition: str = ""
    important_keywords: list[str] = Field(default_factory=list)
    emotional_messaging_direction: str = ""
    what_must_be_avoided_in_messaging: list[str] = Field(default_factory=list)


class BlueprintZone(BaseModel):
    zone_id: str
    role: str
    x: int
    y: int
    width: int
    height: int
    max_lines: int | None = None


class BlueprintPayload(BaseModel):
    layout_type: str
    zones: list[BlueprintZone]
    hierarchy: list[str]
    text_blocks: list[dict[str, Any]]
    image_zones: list[dict[str, Any]]
    logo_rules: dict[str, Any]
    cta_placement: dict[str, Any]
    platform_preset: str
    export_format: str
    overflow_strategy: dict[str, Any]
    source_mode: str = "synthesized_layout"
    source_template_id: str | None = None
    layout_archetype: str | None = None
    adaptation_plan: dict[str, Any] = Field(default_factory=dict)
    brand_rules_applied: dict[str, Any] = Field(default_factory=dict)
    composition_plan: dict[str, Any] = Field(default_factory=dict)


class GeneratedImageAsset(BaseModel):
    asset_id: UUID
    mime_type: str
    storage_path: str
    width: int
    height: int
    asset_role: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreativeDecisionPayload(BaseModel):
    layout_mode: str = "synthesized_layout"
    selected_template_id: str | None = None
    confidence: float = 0.0
    reasoning: list[str] = Field(default_factory=list)
    adaptations: dict[str, Any] = Field(default_factory=dict)
    asset_strategy: dict[str, Any] = Field(default_factory=dict)
    template_candidates: list[dict[str, Any]] = Field(default_factory=list)
    planning_hints: dict[str, Any] = Field(default_factory=dict)


class SceneGraphCanvas(BaseModel):
    width: int
    height: int
    platform: str
    file_type: str | None = None
    safe_margin: int | None = None


class SceneGraphGeometry(BaseModel):
    x: float | int | None = None
    y: float | int | None = None
    width: float | int | None = None
    height: float | int | None = None
    units: str = "normalized"
    anchor: str | None = None
    z_index: int | None = None
    padding: dict[str, float | int] = Field(default_factory=dict)


class SceneGraphAssetBinding(BaseModel):
    asset_id: str | None = None
    asset_role: str | None = None
    storage_path: str | None = None
    trust_level: str | None = None
    variant: str | None = None
    notes: str | None = None


class SceneGraphElement(BaseModel):
    element_id: str
    element_type: str
    role: str
    layer: str = "content"
    geometry: SceneGraphGeometry = Field(default_factory=SceneGraphGeometry)
    text: str | list[str] | None = None
    visible: bool = True
    style: dict[str, Any] = Field(default_factory=dict)
    asset: SceneGraphAssetBinding | None = None
    validation_hints: dict[str, Any] = Field(default_factory=dict)
    visual_metadata: dict[str, Any] | None = None  # 🔥 PHASE 5: Visual hierarchy info


class GenerationSceneGraph(BaseModel):
    version: str = "1.0"
    canvas: SceneGraphCanvas
    layout_mode: str = "synthesized_layout"
    confidence: float = 0.0
    layers: list[str] = Field(default_factory=list)
    elements: list[SceneGraphElement] = Field(default_factory=list)
    styles: dict[str, Any] = Field(default_factory=dict)
    assets: list[SceneGraphAssetBinding] = Field(default_factory=list)
    template_adaptation: dict[str, Any] = Field(default_factory=dict)
    validation_hints: dict[str, Any] = Field(default_factory=dict)


class SceneGraphValidationIssue(BaseModel):
    severity: str
    rule_id: str
    element_id: str | None = None
    message: str
    expected_correction: str | None = None
    repairable: bool = True


class SceneGraphValidationReport(BaseModel):
    status: str = "clean"
    issues: list[SceneGraphValidationIssue] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    repairable: bool = True


class AIOrchestrationResponse(BaseModel):
    message_strategy: MessageStrategyPayload = Field(default_factory=MessageStrategyPayload)
    text: StructuredTextPayload
    creative_decision: CreativeDecisionPayload
    scene_graph: GenerationSceneGraph
    validation_report: SceneGraphValidationReport = Field(default_factory=SceneGraphValidationReport)
    repair_attempts: int = 0
    blueprint: BlueprintPayload
    image_assets: list[GeneratedImageAsset] = Field(default_factory=list)
    final_render_assets: list[GeneratedImageAsset] = Field(default_factory=list)
    final_render_asset: GeneratedImageAsset | None = None
    render_authority: str = "backend"
    explainability: dict[str, Any]
    tone_analysis: dict[str, Any]
    generation_trace: GenerationTrace | None = None


class RendererInput(BaseModel):
    tenant_id: UUID
    brand_space_id: UUID
    content_version_id: UUID
    studio_panel: dict[str, Any]
    blueprint: BlueprintPayload | None = None
    scene_graph: GenerationSceneGraph | None = None
    text: StructuredTextPayload
    template_metadata: dict[str, Any] | None = None
    template_asset_path: str | None = None
    base_canvas_asset_path: str | None = None
    logo_asset_path: str | None = None
    image_assets: list[GeneratedImageAsset] = Field(default_factory=list)
    decorative_assets: list[GeneratedImageAsset] = Field(default_factory=list)
    font_asset_paths: list[str] = Field(default_factory=list)
    brand_visual_rules: dict[str, Any] = Field(default_factory=dict)
    layout_decision: dict[str, Any] = Field(default_factory=dict)
    creative_decision: dict[str, Any] = Field(default_factory=dict)
    validation_report: dict[str, Any] = Field(default_factory=dict)


class RendererResponse(BaseModel):
    preview_asset: dict[str, Any] | None = None
    export_assets: list[dict[str, Any]] = Field(default_factory=list)
    renderer_metadata: dict[str, Any]


class GenerationTrace(BaseModel):
    """
    Tracks all generation decisions for debugging and evaluation.
    Provides full traceability of why specific design choices were made.
    """
    provider: str
    model: str
    fallback_used: bool = False
    layout_source: str  # "brand_design_system" | "reference_template" | "synthesized"
    layout_reason: str
    background_source: str
    cta_source: str  # "brand_cta_template" | "text_payload" | "inferred"
    legal_source: str  # "brand_legal_asset" | "none"
    rag_embedding_type: str  # "openai" | "hash"
    renderer_policy: str  # "instagram_square_default" | etc
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
