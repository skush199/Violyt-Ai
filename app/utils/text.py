from __future__ import annotations

import re
from datetime import datetime, timezone


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")


def current_period_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")

