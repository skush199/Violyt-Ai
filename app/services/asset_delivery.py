from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class AssetDeliveryService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _b64encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    @staticmethod
    def _b64decode(raw: str) -> bytes:
        padding = "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(f"{raw}{padding}".encode("utf-8"))

    def _signature(self, payload: bytes) -> str:
        digest = hmac.new(
            self.settings.secret_key.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).digest()
        return self._b64encode(digest)

    def issue_token(
        self,
        *,
        storage_path: str,
        filename: str | None = None,
        download: bool = False,
        expires_in: int | None = None,
    ) -> str:
        expiry = datetime.now(timezone.utc) + timedelta(
            seconds=expires_in or self.settings.signed_asset_url_ttl_seconds
        )
        payload = {
            "storage_path": storage_path,
            "filename": filename or Path(storage_path).name,
            "download": bool(download),
            "exp": int(expiry.timestamp()),
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return f"{self._b64encode(raw)}.{self._signature(raw)}"

    def build_signed_url(
        self,
        *,
        storage_path: str,
        filename: str | None = None,
        download: bool = False,
        expires_in: int | None = None,
    ) -> str:
        token = self.issue_token(
            storage_path=storage_path,
            filename=filename,
            download=download,
            expires_in=expires_in,
        )
        return f"{self.settings.asset_download_base_url}?token={token}"

    def verify_token(self, token: str) -> dict[str, Any]:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
        except ValueError as exc:
            raise ValueError("Malformed asset token") from exc

        payload_bytes = self._b64decode(encoded_payload)
        expected_signature = self._signature(payload_bytes)
        if not hmac.compare_digest(encoded_signature, expected_signature):
            raise ValueError("Invalid asset signature")

        payload = json.loads(payload_bytes.decode("utf-8"))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("Asset token expired")
        return payload
