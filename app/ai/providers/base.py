from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PromptEnvelope:
    system: str
    user: str


class TextGenerationProvider(ABC):
    provider_name: str

    @abstractmethod
    def generate_structured_json(self, envelope: PromptEnvelope, fallback: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate_text(self, envelope: PromptEnvelope, fallback: str) -> str:
        raise NotImplementedError


class ImageGenerationBackend(ABC):
    provider_name: str

    @abstractmethod
    def generate(self, tenant_id, brand_space_id, prompt: str, size: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def edit(
        self,
        tenant_id,
        brand_space_id,
        prompt: str,
        image_paths: list[str],
        size: str | None = None,
        mask_png_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError
