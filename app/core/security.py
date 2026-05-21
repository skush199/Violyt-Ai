from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any
from uuid import UUID
import secrets as py_secrets

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _bcrypt_secret(password: str) -> bytes:
    # bcrypt only supports the first 72 bytes. Truncating consistently avoids
    # backend-specific crashes while preserving verification behavior.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return pwd_context.hash(_bcrypt_secret(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(_bcrypt_secret(plain_password), hashed_password)


def create_token(
    subject: str,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    payload_extra = {"typ": "access"}
    if extra:
        payload_extra.update(extra)
    return create_token(
        subject=str(user_id),
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra=payload_extra,
    )


def create_refresh_token(user_id: UUID, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    payload_extra = {"typ": "refresh"}
    if extra:
        payload_extra.update(extra)
    return create_token(
        subject=str(user_id),
        expires_delta=timedelta(minutes=settings.refresh_token_expire_minutes),
        extra=payload_extra,
    )


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def generate_totp_secret() -> str:
    return base64.b32encode(py_secrets.token_bytes(20)).decode("utf-8").rstrip("=")


def _decode_totp_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def generate_totp_code(
    secret: str,
    *,
    for_time: datetime | None = None,
    period: int = 30,
    digits: int = 6,
) -> str:
    current_time = for_time or datetime.now(timezone.utc)
    counter = int(current_time.timestamp()) // period
    counter_bytes = counter.to_bytes(8, "big")
    digest = hmac.new(_decode_totp_secret(secret), counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def verify_totp_code(
    secret: str,
    code: str,
    *,
    at_time: datetime | None = None,
    period: int = 30,
    digits: int = 6,
    window: int = 1,
) -> bool:
    if not code.isdigit() or len(code) != digits:
        return False
    current_time = at_time or datetime.now(timezone.utc)
    for step in range(-window, window + 1):
        candidate_time = current_time + timedelta(seconds=step * period)
        if generate_totp_code(secret, for_time=candidate_time, period=period, digits=digits) == code:
            return True
    return False
