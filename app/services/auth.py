from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    generate_totp_secret,
    hash_password,
    verify_password,
    verify_totp_code,
)
from app.models.tenant import ActivationToken
from app.repositories.tenant import ActivationTokenRepository, UserRepository, UserRoleRepository
from app.schemas.auth import (
    CurrentUserResponse,
    PasswordResetResponse,
    TokenPairResponse,
    TwoFactorChallengeResponse,
    TwoFactorSetupResponse,
)
from app.services.email import EmailService


class AuthService:
    TWO_FACTOR_ENABLED_KEY = "two_factor_enabled"
    TWO_FACTOR_SECRET_KEY = "two_factor_secret"
    TWO_FACTOR_PENDING_SECRET_KEY = "two_factor_pending_secret"
    TWO_FACTOR_VERIFIED_AT_KEY = "two_factor_verified_at"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.user_roles = UserRoleRepository(session)
        self.tokens = ActivationTokenRepository(session)
        self.email = EmailService()

    async def login(self, email: str, password: str) -> TokenPairResponse | TwoFactorChallengeResponse:
        user = await self.users.get_by_email(email)
        if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
        if self.is_two_factor_enabled(user):
            ticket = create_token(
                subject=str(user.id),
                expires_delta=timedelta(minutes=10),
                extra={
                    "tenant_id": str(user.tenant_id) if user.tenant_id else None,
                    "typ": "two_factor",
                },
            )
            return TwoFactorChallengeResponse(two_factor_ticket=ticket, email=user.email)
        return await self._complete_login(user)

    async def verify_two_factor_login(self, ticket: str, code: str) -> TokenPairResponse:
        try:
            payload = decode_token(ticket)
            if payload.get("typ") != "two_factor":
                raise ValueError("Invalid token type")
            user_id = UUID(payload["sub"])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 2FA challenge") from exc
        user = await self.users.get(user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        secret = self.get_two_factor_secret(user)
        if not secret or not verify_totp_code(secret, code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
        return await self._complete_login(user)

    async def refresh_access_token(self, refresh_token: str) -> TokenPairResponse:
        try:
            payload = decode_token(refresh_token)
            token_type = str(payload.get("typ") or "").strip().lower()
            if token_type and token_type != "refresh":
                raise ValueError("Invalid token type")
            user_id = UUID(payload["sub"])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

        user = await self.users.get(user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

        return await self._complete_login(user)

    async def get_two_factor_status(self, user_id) -> TwoFactorSetupResponse:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        metadata = user.metadata_json or {}
        return TwoFactorSetupResponse(
            enabled=self.is_two_factor_enabled(user),
            pending_setup=bool(metadata.get(self.TWO_FACTOR_PENDING_SECRET_KEY)),
        )

    async def initiate_two_factor_setup(self, user_id) -> TwoFactorSetupResponse:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        secret = generate_totp_secret()
        metadata = {
            **(user.metadata_json or {}),
            self.TWO_FACTOR_PENDING_SECRET_KEY: secret,
        }
        user.metadata_json = metadata
        await self.session.commit()
        otpauth_url = self.build_otpauth_url(user.email, secret)
        return TwoFactorSetupResponse(
            enabled=self.is_two_factor_enabled(user),
            pending_setup=True,
            secret=secret,
            otpauth_url=otpauth_url,
            qr_code_url=self.build_qr_code_url(otpauth_url),
        )

    async def enable_two_factor(self, user_id, code: str) -> TwoFactorSetupResponse:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        metadata = user.metadata_json or {}
        pending_secret = metadata.get(self.TWO_FACTOR_PENDING_SECRET_KEY)
        if not pending_secret:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Two-factor setup has not been started")
        if not verify_totp_code(pending_secret, code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
        user.metadata_json = {
            **metadata,
            self.TWO_FACTOR_SECRET_KEY: pending_secret,
            self.TWO_FACTOR_ENABLED_KEY: True,
            self.TWO_FACTOR_VERIFIED_AT_KEY: datetime.now(timezone.utc).isoformat(),
            self.TWO_FACTOR_PENDING_SECRET_KEY: None,
        }
        await self.session.commit()
        await self.session.refresh(user)
        return TwoFactorSetupResponse(enabled=True, pending_setup=False)

    async def disable_two_factor(self, user_id, code: str) -> TwoFactorSetupResponse:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        secret = self.get_two_factor_secret(user)
        if not secret or not verify_totp_code(secret, code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
        metadata = {
            **(user.metadata_json or {}),
            self.TWO_FACTOR_SECRET_KEY: None,
            self.TWO_FACTOR_ENABLED_KEY: False,
            self.TWO_FACTOR_PENDING_SECRET_KEY: None,
        }
        user.metadata_json = metadata
        await self.session.commit()
        await self.session.refresh(user)
        return TwoFactorSetupResponse(enabled=False, pending_setup=False)

    async def _complete_login(self, user) -> TokenPairResponse:
        user.last_login_at = datetime.now(timezone.utc)
        await self.session.commit()
        access = create_access_token(user.id, extra={"tenant_id": str(user.tenant_id) if user.tenant_id else None})
        refresh = create_refresh_token(user.id, extra={"tenant_id": str(user.tenant_id) if user.tenant_id else None})
        return TokenPairResponse(access_token=access, refresh_token=refresh)

    async def activate(self, token: str, password: str) -> TokenPairResponse:
        activation = await self.tokens.get_by_token(token)
        if not activation or activation.used_at or activation.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid activation token")
        user = await self.users.get(activation.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid activation token")
        user.hashed_password = hash_password(password)
        user.is_activated = True
        activation.used_at = datetime.now(timezone.utc)
        await self.session.commit()
        access = create_access_token(user.id, extra={"tenant_id": str(user.tenant_id) if user.tenant_id else None})
        refresh = create_refresh_token(user.id, extra={"tenant_id": str(user.tenant_id) if user.tenant_id else None})
        return TokenPairResponse(access_token=access, refresh_token=refresh)

    async def forgot_password(self, email: str) -> PasswordResetResponse:
        user = await self.users.get_by_email(email)
        if not user or not user.is_active:
            return PasswordResetResponse(message="If the email exists, a reset token has been issued.", reset_token=None)
        token_value = secrets.token_urlsafe(24)
        await self.tokens.add(
            ActivationToken(
                user_id=user.id,
                token=token_value,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
                used_at=None,
            )
        )
        await self.session.commit()
        delivery = self.email.send_password_reset_email(user.email, user.full_name, token_value)
        return PasswordResetResponse(
            message="If the email exists, a reset link has been sent.",
            reset_token=token_value if not delivery.delivered else None,
        )

    async def reset_password(self, token: str, password: str) -> TokenPairResponse:
        return await self.activate(token, password)

    async def update_profile(
        self,
        user_id,
        full_name: str | None,
        email: str | None,
        phone_number: str | None,
        notifications_enabled: bool | None,
    ):
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if full_name is not None:
            user.full_name = full_name
        if email is not None and email != user.email:
            existing = await self.users.get_by_email(email)
            if existing and existing.id != user.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email address is already in use")
            user.email = email
        if phone_number is not None:
            user.phone_number = phone_number
        if notifications_enabled is not None:
            user.metadata_json = {
                **(user.metadata_json or {}),
                "notifications_enabled": notifications_enabled,
            }
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def change_password(self, user_id, current_password: str, new_password: str) -> PasswordResetResponse:
        user = await self.users.get(user_id)
        if not user or not user.hashed_password:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is invalid")
        user.hashed_password = hash_password(new_password)
        await self.session.commit()
        return PasswordResetResponse(message="Password updated successfully.")

    async def delete_profile(self, user_id) -> PasswordResetResponse:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.is_active = False
        await self.session.commit()
        return PasswordResetResponse(message="Account deleted successfully.")

    async def build_current_user_response(self, user_id, role_codes: list[str], brand_space_ids: list) -> CurrentUserResponse:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return CurrentUserResponse(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            full_name=user.full_name,
            role_codes=role_codes,
            assigned_brand_space_ids=brand_space_ids,
            extra={
                "phone_number": user.phone_number,
                "notifications_enabled": (user.metadata_json or {}).get("notifications_enabled", True),
                "two_factor_enabled": self.is_two_factor_enabled(user),
            },
        )

    def is_two_factor_enabled(self, user) -> bool:
        metadata = user.metadata_json or {}
        return bool(metadata.get(self.TWO_FACTOR_ENABLED_KEY) and metadata.get(self.TWO_FACTOR_SECRET_KEY))

    def get_two_factor_secret(self, user) -> str | None:
        metadata = user.metadata_json or {}
        secret = metadata.get(self.TWO_FACTOR_SECRET_KEY)
        return secret if isinstance(secret, str) else None

    @staticmethod
    def build_otpauth_url(email: str, secret: str) -> str:
        issuer = "Violyt"
        return (
            f"otpauth://totp/{quote(issuer)}:{quote(email)}"
            f"?secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
        )

    @staticmethod
    def build_qr_code_url(otpauth_url: str) -> str:
        return f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={quote(otpauth_url, safe='')}"
