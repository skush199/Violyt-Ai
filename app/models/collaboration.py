from __future__ import annotations

from uuid import UUID

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import (
    BrandScopedMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ReviewLink(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "review_links"

    content_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_history.id", ondelete="CASCADE"),
        index=True,
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    allow_external_comments: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class ReviewComment(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "review_comments"

    review_link_id: Mapped[UUID] = mapped_column(ForeignKey("review_links.id", ondelete="CASCADE"), index=True)
    author_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    external_author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class SocialConnection(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "social_connections"
    __table_args__ = (UniqueConstraint("brand_space_id", "platform", name="uq_brand_platform_connection"),)

    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AnalyticsSnapshot(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "analytics"

    metric_scope: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metric_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class UsageLimit(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "usage_limits"

    max_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_brand_spaces: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_content_generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_image_generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_ocr_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UsageConsumption(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "usage_consumption"
    __table_args__ = (
        UniqueConstraint("tenant_id", "metric_code", "period_key", name="uq_usage_metric_period"),
    )

    metric_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    period_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class JobRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "jobs"

    content_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_history.id", ondelete="SET NULL"),
        nullable=True,
    )
    knowledge_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued", index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
