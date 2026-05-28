from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import APIModel


class BrandIdentityPayload(APIModel):
    brand_name: str
    brand_description: str
    industry_category: str | None = None
    sub_industry: str | None = None
    target_geography: dict[str, str] = Field(default_factory=dict)
    audience_type: str | None = None
    key_differentiators: list[str] = Field(default_factory=list)
    logo_asset_id: UUID | None = None
    logo_asset_ids: list[UUID] = Field(default_factory=list)
    website_url: str | None = None
    social_profiles: dict[str, str] = Field(default_factory=dict)


class BrandFoundationsPayload(APIModel):
    brand_mission: str | None = None
    brand_vision: str | None = None
    brand_promise: str | None = None
    market_positioning: str | None = None
    role_of_digital_platforms: str | None = None
    social_media_challenges: list[str] = Field(default_factory=list)
    business_problem_or_opportunity: str | None = None
    perception_challenge: str | None = None
    human_insight: str | None = None
    brand_advantage: str | None = None
    industry_context: dict[str, Any] = Field(default_factory=dict)


class BrandVoicePayload(APIModel):
    tone_attributes: list[str] = Field(default_factory=list)
    tone_intensity: dict[str, int] = Field(default_factory=dict)
    primary_emotion: str
    secondary_emotion: str | None = None
    avoided_emotion: str | None = None
    content_complexity: str | None = None
    sentence_length: str | None = None
    perspective: str | None = None


class PersonaPayload(APIModel):
    name: str
    role: str | None = None
    psychographics: dict[str, Any] = Field(default_factory=dict)
    demographics: dict[str, Any] = Field(default_factory=dict)
    audience_goals: list[str] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    fears_and_pain_points: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    content_behavior: dict[str, Any] = Field(default_factory=dict)
    language_preference: str | None = None
    is_default: bool = False


class GuardrailPayload(APIModel):
    positive_word_bank: list[str] = Field(default_factory=list)
    replaceable_words: list[str] = Field(default_factory=list)
    negative_word_bank: list[str] = Field(default_factory=list)
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    forbidden_prompt_patterns: list[str] = Field(default_factory=list)
    restricted_topics: list[str] = Field(default_factory=list)
    restricted_claims: list[str] = Field(default_factory=list)
    blocked_words: list[str] = Field(default_factory=list)
    custom_rules: list[str] = Field(default_factory=list)
    positive_word_bank_asset_ids: list[UUID] = Field(default_factory=list)
    negative_word_bank_asset_ids: list[UUID] = Field(default_factory=list)
    replaceable_word_bank_asset_ids: list[UUID] = Field(default_factory=list)


class ObjectivePayload(APIModel):
    name: str
    description: str | None = None
    content_type: str | None = None
    platform_scope: str | None = None
    is_default: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)


LOGO_PLACEMENT_OPTIONS = {
    "top-right",
    "top-left",
    "bottom-right",
    "bottom-left",
    "top-center",
    "bottom-center",
    "center",
}


def normalize_logo_placement_option(value: Any) -> str:
    raw_value = str(value or "").strip().lower()
    if not raw_value:
        return ""
    normalized = raw_value.replace("_", "-").replace(" ", "-")
    if normalized in LOGO_PLACEMENT_OPTIONS:
        return normalized

    tokens = raw_value.replace("_", " ").replace("-", " ").split()
    token_set = set(tokens)
    has_top = "top" in token_set or "upper" in token_set
    has_bottom = "bottom" in token_set or "lower" in token_set
    has_left = "left" in token_set
    has_right = "right" in token_set
    has_center = "center" in token_set or "middle" in token_set or "centre" in token_set

    if has_center and not (has_top or has_bottom or has_left or has_right):
        return "center"
    vertical = "top" if has_top else "bottom" if has_bottom else ""
    horizontal = "left" if has_left else "right" if has_right else "center" if has_center else ""
    if vertical and horizontal:
        candidate = f"{vertical}-{horizontal}"
        return candidate if candidate in LOGO_PLACEMENT_OPTIONS else ""
    return ""


class LogoPlacementPayload(APIModel):
    allowed_positions: list[Any] = Field(default_factory=list)
    default_position: Any = ""

    @model_validator(mode="after")
    def normalize_policy(self) -> "LogoPlacementPayload":
        allowed_positions: list[str] = []
        for raw_position in self.allowed_positions:
            normalized = normalize_logo_placement_option(raw_position)
            if not normalized:
                raise ValueError(f"Invalid logo placement position: {raw_position!r}")
            if normalized not in allowed_positions:
                allowed_positions.append(normalized)

        default_position = normalize_logo_placement_option(self.default_position)
        if default_position and not allowed_positions:
            allowed_positions.append(default_position)
        if allowed_positions and not default_position:
            default_position = allowed_positions[0]
        if default_position and default_position not in allowed_positions:
            raise ValueError("Default logo position must be one of the allowed logo positions.")

        self.allowed_positions = allowed_positions
        self.default_position = default_position
        return self


class VisualIdentityPayload(APIModel):
    brand_mood: str | None = None
    visual_style: str | None = None
    logo_placement: LogoPlacementPayload = Field(default_factory=LogoPlacementPayload)
    brand_color_palette: dict[str, str] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    reference_creative_asset_ids: list[UUID] = Field(default_factory=list)
    mood_board_asset_ids: list[UUID] = Field(default_factory=list)
    color_palette_asset_ids: list[UUID] = Field(default_factory=list)
    font_guide_asset_ids: list[UUID] = Field(default_factory=list)


class PromptIntelligencePayload(APIModel):
    prompt_starters: list[dict[str, Any]] = Field(default_factory=list)
    platform_rules: dict[str, Any] = Field(default_factory=dict)


class BrandSectionUpsertRequest(APIModel):
    section_code: str
    payload: dict[str, Any]
    completion_percent: int = Field(default=100, ge=0, le=100)

    @model_validator(mode="after")
    def normalize_section_payload(self) -> "BrandSectionUpsertRequest":
        if self.section_code != "visual_identity":
            return self
        payload = dict(self.payload or {})
        payload["logo_placement"] = LogoPlacementPayload.model_validate(
            payload.get("logo_placement") or {}
        ).model_dump()
        self.payload = payload
        return self


class BrandCreateRequest(APIModel):
    identity: BrandIdentityPayload
    foundations: BrandFoundationsPayload | None = None
    voice_tone: BrandVoicePayload | None = None


class BrandUpdateRequest(APIModel):
    description: str | None = None
    lifecycle_state: str | None = None
    overview_snapshot: dict[str, Any] | None = None


class BrandFinalizeRequest(APIModel):
    review_notes: str | None = None


class BrandResponse(APIModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    description: str
    lifecycle_state: str
    is_finalized: bool
    resolved_brand_context: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class BrandOverviewResponse(APIModel):
    brand: BrandResponse
    sections: list[dict[str, Any]]
    personas: list[dict[str, Any]]
    guardrails: list[dict[str, Any]]
    objectives: list[dict[str, Any]]
