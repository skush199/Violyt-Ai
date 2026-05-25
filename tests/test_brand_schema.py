from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.brand import BrandSectionUpsertRequest


def test_visual_identity_section_normalizes_logo_placement_policy() -> None:
    request = BrandSectionUpsertRequest.model_validate(
        {
            "section_code": "visual_identity",
            "payload": {
                "logo_placement": {
                    "allowed_positions": ["top left", "top-left"],
                    "default_position": "top left",
                }
            },
            "completion_percent": 100,
        }
    )

    assert request.payload["logo_placement"] == {
        "allowed_positions": ["top-left"],
        "default_position": "top-left",
    }


def test_visual_identity_section_rejects_default_outside_allowed_logo_positions() -> None:
    with pytest.raises(ValidationError):
        BrandSectionUpsertRequest.model_validate(
            {
                "section_code": "visual_identity",
                "payload": {
                    "logo_placement": {
                        "allowed_positions": ["top-left"],
                        "default_position": "bottom-right",
                    }
                },
                "completion_percent": 100,
            }
        )
