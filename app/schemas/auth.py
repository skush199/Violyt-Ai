from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import APIModel


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=8)


class ActivationRequest(APIModel):
    token: str
    password: str = Field(min_length=8)


class ForgotPasswordRequest(APIModel):
    email: EmailStr


class ResetPasswordRequest(APIModel):
    token: str
    password: str = Field(min_length=8)


class RefreshTokenRequest(APIModel):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(APIModel):
    current_password: str = Field(min_length=8)
    new_password: str = Field(min_length=8)


class ProfileUpdateRequest(APIModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone_number: str | None = None
    notifications_enabled: bool | None = None


class TokenPairResponse(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TwoFactorChallengeResponse(APIModel):
    requires_two_factor: bool = True
    two_factor_ticket: str
    delivery: str = "authenticator"
    email: EmailStr


AuthLoginResponse = TokenPairResponse | TwoFactorChallengeResponse


class PasswordResetResponse(APIModel):
    message: str
    reset_token: str | None = None


class TwoFactorVerifyRequest(APIModel):
    ticket: str
    code: str = Field(min_length=6, max_length=6)


class TwoFactorCodeRequest(APIModel):
    code: str = Field(min_length=6, max_length=6)


class TwoFactorSetupResponse(APIModel):
    enabled: bool
    pending_setup: bool
    secret: str | None = None
    otpauth_url: str | None = None
    qr_code_url: str | None = None


class CurrentUserResponse(APIModel):
    user_id: UUID
    tenant_id: UUID | None = None
    email: EmailStr
    full_name: str
    role_codes: list[str]
    assigned_brand_space_ids: list[UUID]
    extra: dict[str, Any] = Field(default_factory=dict)
