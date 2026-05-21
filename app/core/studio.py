from __future__ import annotations

from copy import deepcopy


DEFAULT_PLATFORM_SIZES: dict[str, dict[str, int]] = {
    "instagram": {"width": 1080, "height": 1080},
    "linkedin": {"width": 1200, "height": 627},
    "x": {"width": 1600, "height": 900},
    "youtube_thumbnail": {"width": 1280, "height": 720},
}


FORMAT_OVERRIDES: dict[str, dict[str, int]] = {
    "pdf": {"width": 1240, "height": 1754},
    "infographic": {"width": 1080, "height": 1920},
}


CAROUSEL_OVERRIDES: dict[str, dict[str, int]] = {
    "instagram": {"width": 1080, "height": 1350},
    "linkedin": {"width": 1200, "height": 1200},
    "x": {"width": 1600, "height": 900},
    "youtube_thumbnail": {"width": 1280, "height": 720},
}


def resolve_studio_panel_defaults(panel: dict) -> dict:
    resolved = deepcopy(panel or {})
    format_name = str(resolved.get("format") or "static").lower()
    platform = str(resolved.get("platform_preset") or "instagram").lower()
    size = resolved.get("size") or {}

    if format_name == "carousel":
        default_size = CAROUSEL_OVERRIDES.get(platform, CAROUSEL_OVERRIDES["instagram"])
    elif format_name in FORMAT_OVERRIDES:
        default_size = FORMAT_OVERRIDES[format_name]
    else:
        default_size = DEFAULT_PLATFORM_SIZES.get(platform, DEFAULT_PLATFORM_SIZES["instagram"])

    resolved["size"] = {
        "width": size.get("width", default_size["width"]),
        "height": size.get("height", default_size["height"]),
    }
    resolved["platform_preset"] = platform
    resolved["format"] = format_name
    resolved["file_type"] = str(resolved.get("file_type") or "png").lower()
    return resolved
