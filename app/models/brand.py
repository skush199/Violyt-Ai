from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import (
    BrandScopedMixin,
    SoftDeleteMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class BrandSpace(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "brand_spaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    industry_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sub_industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geography_country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geography_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audience_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overview_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    resolved_brand_context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    default_persona_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personas.id", ondelete="SET NULL"),
        nullable=True,
    )

    sections: Mapped[list["BrandConfigurationSection"]] = relationship(
        back_populates="brand_space",
        cascade="all, delete-orphan",
    )
    personas: Mapped[list["Persona"]] = relationship(
        back_populates="brand_space",
        cascade="all, delete-orphan",
        foreign_keys="Persona.brand_space_id",
    )
    guardrails: Mapped[list["Guardrail"]] = relationship(
        back_populates="brand_space",
        cascade="all, delete-orphan",
    )
    objectives: Mapped[list["Objective"]] = relationship(
        back_populates="brand_space",
        cascade="all, delete-orphan",
    )
    members: Mapped[list["BrandSpaceMember"]] = relationship(
        back_populates="brand_space",
        cascade="all, delete-orphan",
    )


class BrandConfigurationSection(
    UUIDPrimaryKeyMixin,
    TenantScopedMixin,
    BrandScopedMixin,
    TimestampMixin,
    Base,
):
    __tablename__ = "brand_configuration_sections"
    __table_args__ = (
        UniqueConstraint("brand_space_id", "section_code", "version", name="uq_brand_section_version"),
    )

    section_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    completion_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    brand_space: Mapped["BrandSpace"] = relationship(back_populates="sections")


class Persona(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "personas"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    psychographics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    demographics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    audience_goals: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    motivations: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    fears_and_pain_points: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    objections: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    content_behavior: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    language_preference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    brand_space: Mapped["BrandSpace"] = relationship(
        back_populates="personas",
        foreign_keys="Persona.brand_space_id",
    )


class Guardrail(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "guardrails"

    positive_word_bank: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    replaceable_words: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    negative_word_bank: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    dos: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    donts: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    forbidden_prompt_patterns: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    restricted_topics: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    restricted_claims: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    blocked_words: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    custom_rules: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    brand_space: Mapped["BrandSpace"] = relationship(back_populates="guardrails")


class Objective(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "objectives"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    platform_scope: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    brand_space: Mapped["BrandSpace"] = relationship(back_populates="objectives")


class BrandSpaceMember(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "brand_space_members"
    __table_args__ = (UniqueConstraint("brand_space_id", "user_id", name="uq_brand_member"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    can_manage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    brand_space: Mapped["BrandSpace"] = relationship(back_populates="members")
