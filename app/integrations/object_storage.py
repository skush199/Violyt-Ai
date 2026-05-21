from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from uuid import uuid4

from app.core.config import get_settings
from app.utils.files import ensure_parent, sanitize_filename


@dataclass(slots=True)
class StoredObject:
    storage_path: str
    absolute_path: str


class LocalObjectStorage:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_path = Path(self.settings.object_storage_base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_segment(value: str, *, fallback: str) -> str:
        cleaned = sanitize_filename(value, fallback=fallback, max_length=80)
        return cleaned.replace(".", "-").strip("-") or fallback

    def _generate_object_name(self, filename: str) -> str:
        cleaned = sanitize_filename(filename, fallback="file", max_length=96)
        suffix = Path(cleaned).suffix.lower()
        stem = Path(cleaned).stem or "file"
        return f"{stem[:48]}-{uuid4().hex}{suffix}"

    def _resolve_storage_path(self, storage_path: str) -> Path:
        resolved = (self.base_path / storage_path).resolve()
        if not str(resolved).startswith(str(self.base_path)):
            raise ValueError("Resolved storage path is outside the configured storage root")
        return resolved

    def build_relative_path(
        self,
        tenant_id: UUID,
        brand_space_id: UUID | None,
        category: str,
        filename: str,
    ) -> str:
        brand_component = str(brand_space_id) if brand_space_id else "global"
        category_parts = [part for part in str(category or "").replace("\\", "/").split("/") if part.strip()]
        safe_parts = [
            self._safe_segment(part, fallback="files")
            for part in category_parts
        ] or ["files"]
        object_name = self._generate_object_name(filename)
        category_path = "/".join(safe_parts)
        return f"{tenant_id}/{brand_component}/{category_path}/{object_name}"

    def save_bytes(
        self,
        tenant_id: UUID,
        brand_space_id: UUID | None,
        category: str,
        filename: str,
        content: bytes,
    ) -> StoredObject:
        relative_path = self.build_relative_path(tenant_id, brand_space_id, category, filename)
        absolute_path = self._resolve_storage_path(relative_path)
        ensure_parent(absolute_path)
        absolute_path.write_bytes(content)
        return StoredObject(storage_path=relative_path, absolute_path=str(absolute_path))

    def read_bytes(self, storage_path: str) -> bytes:
        return self._resolve_storage_path(storage_path).read_bytes()

    def exists(self, storage_path: str) -> bool:
        try:
            return self._resolve_storage_path(storage_path).exists()
        except ValueError:
            return False

    def delete(self, storage_path: str) -> None:
        path = self._resolve_storage_path(storage_path)
        if path.exists():
            path.unlink()

    def absolute_path(self, storage_path: str) -> str:
        return str(self._resolve_storage_path(storage_path))
