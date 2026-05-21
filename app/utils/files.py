from __future__ import annotations

import base64
import binascii
from pathlib import Path
import re


_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def estimate_decoded_base64_size(content_base64: str) -> int:
    encoded = content_base64.split(",", 1)[1] if "," in content_base64 else content_base64
    stripped = "".join(encoded.split())
    padding = stripped.count("=")
    return max(((len(stripped) * 3) // 4) - padding, 0)


def decode_base64_content(content_base64: str, *, max_bytes: int | None = None) -> bytes:
    if "," in content_base64:
        _, encoded = content_base64.split(",", 1)
    else:
        encoded = content_base64
    if max_bytes is not None and estimate_decoded_base64_size(encoded) > max_bytes:
        raise ValueError(f"Decoded file exceeds the {max_bytes} byte limit")
    try:
        return base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:  # pragma: no cover - validation guard
        raise ValueError("Upload content is not valid base64") from exc


def sanitize_filename(filename: str, *, fallback: str = "file", max_length: int = 160) -> str:
    raw_name = Path(filename or fallback).name
    stem = _SAFE_FILENAME_CHARS.sub("-", Path(raw_name).stem).strip(" ._-")
    suffix = _SAFE_FILENAME_CHARS.sub("", Path(raw_name).suffix)
    cleaned_stem = stem or fallback
    allowed_length = max(max_length - len(suffix), len(fallback))
    return f"{cleaned_stem[:allowed_length]}{suffix}"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
