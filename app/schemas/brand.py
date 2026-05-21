from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

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


class VisualIdentityPayload(APIModel):
    brand_mood: str | None = None
    visual_style: str | None = None
    logo_placement: dict[str, Any] = Field(default_factory=dict)
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
