from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_social_encryption_key


def _fernet() -> Fernet:
    return Fernet(get_social_encryption_key())


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
