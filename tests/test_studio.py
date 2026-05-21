from app.core.studio import resolve_studio_panel_defaults


def test_resolve_studio_panel_defaults_adds_x_platform_size() -> None:
    resolved = resolve_studio_panel_defaults({"format": "static", "platform_preset": "x", "file_type": "png"})
    assert resolved["size"] == {"width": 1600, "height": 900}


def test_resolve_studio_panel_defaults_adds_infographic_size() -> None:
    resolved = resolve_studio_panel_defaults({"format": "infographic", "platform_preset": "instagram", "file_type": "png"})
    assert resolved["size"] == {"width": 1080, "height": 1920}

