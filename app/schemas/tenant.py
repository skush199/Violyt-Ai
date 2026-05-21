from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import APIModel


class TenantUsageLimitUpdate(APIModel):
    max_users: int = Field(ge=0)
    max_brand_spaces: int = Field(ge=0)
    max_content_generations: int = Field(ge=0)
    max_image_generations: int = Field(ge=0)
    max_ocr_pages: int = Field(ge=0)


class TenantCreateRequest(APIModel):
    name: str
    slug: str
    contact_email: EmailStr
    contact_number: str | None = None
    address: str | None = None
    admin_full_name: str
    admin_email: EmailStr
    admin_phone_number: str | None = None
    usage_limits: TenantUsageLimitUpdate
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantUpdateRequest(APIModel):
    name: str | None = None
    slug: str | None = None
    contact_email: EmailStr | None = None
    contact_number: str | None = None
    address: str | None = None
    admin_full_name: str | None = None
    admin_email: EmailStr | None = None
    admin_phone_number: str | None = None
    usage_limits: TenantUsageLimitUpdate | None = None
    metadata_json: dict[str, Any] | None = None
    is_active: bool | None = None


class TenantLogoUploadRequest(APIModel):
    filename: str
    mime_type: str
    content_base64: str


class TenantResponse(APIModel):
    id: UUID
    name: str
    slug: str
    contact_email: EmailStr
    contact_number: str | None = None
    address: str | None = None
    logo_asset_path: str | None = None
    is_active: bool
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TenantCreateResponse(TenantResponse):
    activation_email: ActivationEmailStatus


class TenantSummaryResponse(TenantResponse):
    total_users: int = 0
    brand_space_count: int = 0
    usage_limits: TenantUsageLimitUpdate | None = None
    usage_consumption: dict[str, int] = Field(default_factory=dict)
    token_usage: dict[str, int] = Field(default_factory=dict)
    monthly_token_usage: list[dict[str, int | str]] = Field(default_factory=list)
    tenant_admin_name: str | None = None
    tenant_admin_email: EmailStr | None = None
    tenant_admin_phone_number: str | None = None
    last_active_at: datetime | None = None


class TenantUserCreateRequest(APIModel):
    full_name: str
    email: EmailStr
    phone_number: str | None = None
    role_code: str
    brand_space_ids: list[UUID] = Field(default_factory=list)


class TenantUserUpdateRequest(APIModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone_number: str | None = None
    role_code: str | None = None
    brand_space_ids: list[UUID] | None = None
    is_active: bool | None = None


class TenantUserResponse(APIModel):
    id: UUID
    tenant_id: UUID | None = None
    email: EmailStr
    full_name: str
    phone_number: str | None = None
    is_active: bool
    is_activated: bool
    role_codes: list[str]
    brand_space_ids: list[UUID]
    created_at: datetime
    last_login_at: datetime | None = None


class ActivationEmailStatus(APIModel):
    attempted: bool
    delivered: bool
    recipient_email: EmailStr
    reason: str | None = None


class TenantUserCreateResponse(TenantUserResponse):
    activation_email: ActivationEmailStatus


class TenantBrandSpaceSummaryResponse(APIModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    lifecycle_state: str
    created_at: datetime
    last_active_at: datetime | None = None
    last_login_at: datetime | None = None
    content_generations: int = 0
    visual_generations: int = 0
    ocr_pages: int = 0


class TenantUsageSummary(APIModel):
    tenant_id: UUID
    limits: TenantUsageLimitUpdate
    consumption: dict[str, int]
