from __future__ import annotations

import pytest

from app.services.asset_delivery import AssetDeliveryService


def test_asset_delivery_round_trips_signed_token() -> None:
    service = AssetDeliveryService()

    token = service.issue_token(
        storage_path="tenant-a/brand-b/uploads/logo.png",
        filename="logo.png",
        download=True,
        expires_in=60,
    )

    payload = service.verify_token(token)

    assert payload["storage_path"] == "tenant-a/brand-b/uploads/logo.png"
    assert payload["filename"] == "logo.png"
    assert payload["download"] is True


def test_asset_delivery_rejects_tampered_token() -> None:
    service = AssetDeliveryService()
    token = service.issue_token(
        storage_path="tenant-a/brand-b/uploads/logo.png",
        filename="logo.png",
        expires_in=60,
    )

    bad_token = f"{token[:-1]}x"

    with pytest.raises(ValueError):
        service.verify_token(bad_token)
