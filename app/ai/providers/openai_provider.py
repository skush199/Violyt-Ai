from __future__ import annotations

import base64
import json
from io import BytesIO
from contextlib import ExitStack
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.request import urlopen

from openai import OpenAI
from PIL import Image

from app.ai.providers.base import ImageGenerationBackend, PromptEnvelope, TextGenerationProvider
from app.core.config import get_settings
from app.integrations.object_storage import LocalObjectStorage


class OpenAITextProvider(TextGenerationProvider):
    provider_name = "openai"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None

    def generate_structured_json(self, envelope: PromptEnvelope, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.client:
            return fallback
        response = self.client.responses.create(
            model=self.settings.llm_model,
            input=[
                {"role": "system", "content": envelope.system},
                {"role": "user", "content": envelope.user},
            ],
            text={"format": {"type": "json_object"}},
        )
        text = response.output_text or json.dumps(fallback)
        return json.loads(text)

    def generate_text(self, envelope: PromptEnvelope, fallback: str) -> str:
        if not self.client:
            return fallback
        response = self.client.responses.create(
            model=self.settings.tone_model,
            input=[
                {"role": "system", "content": envelope.system},
                {"role": "user", "content": envelope.user},
            ],
        )
        return response.output_text or fallback


class OpenAIImageProvider(ImageGenerationBackend):
    provider_name = "openai"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None
        self.storage = LocalObjectStorage()

    def _image_edit_options(self, size: str) -> dict[str, Any]:
        model_name = str(self.settings.image_model or "").strip().lower()
        options: dict[str, Any] = {
            "model": self.settings.image_model,
            "size": size,
            "output_format": "png",
        }
        # `gpt-image-1-mini` does not currently accept `input_fidelity`, and
        # sending it causes the logo edit pass to fail before the model can
        # apply the real uploaded logo. We also avoid forcing `quality=high`
        # on mini models to keep the logo edit pass as fast as possible.
        if "mini" not in model_name:
            options["quality"] = "high"
            options["input_fidelity"] = "high"
        return options

    def _image_generate_options(self, size: str) -> dict[str, Any]:
        model_name = str(self.settings.image_model or "").strip().lower()
        options: dict[str, Any] = {
            "model": self.settings.image_model,
            "size": size,
        }
        if "mini" not in model_name:
            options["quality"] = "high"
        return options

    @staticmethod
    def _extract_image_bytes(result: Any) -> bytes:
        data = list(getattr(result, "data", []) or [])
        if not data:
            raise RuntimeError("OpenAI image response did not contain any image data")
        item = data[0]
        image_b64 = getattr(item, "b64_json", None) or getattr(item, "b64", None)
        if image_b64:
            return base64.b64decode(image_b64)
        image_url = getattr(item, "url", None)
        if image_url:
            with urlopen(image_url, timeout=120) as response:  # noqa: S310 - trusted provider URL
                return response.read()
        raise RuntimeError("OpenAI image response did not include retrievable image bytes")

    def generate(self, tenant_id, brand_space_id, prompt: str, size: str | None = None) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("OpenAI image provider unavailable")
        result = self.client.images.generate(
            prompt=prompt,
            **self._image_generate_options(size or "1024x1024"),
        )
        image_bytes = self._extract_image_bytes(result)
        image = Image.open(BytesIO(image_bytes))
        stored = self.storage.save_bytes(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            category="generated",
            filename=f"generated-{brand_space_id}.png",
            content=image_bytes,
        )
        return {
            "mime_type": "image/png",
            "storage_path": stored.storage_path,
            "width": image.width,
            "height": image.height,
            "asset_role": "ai_image",
            "provider": self.provider_name,
            "model": self.settings.image_model,
            "size": size or "1024x1024",
        }

    def edit(
        self,
        tenant_id,
        brand_space_id,
        prompt: str,
        image_paths: list[str],
        size: str | None = None,
        mask_png_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("OpenAI image provider unavailable")
        if not image_paths:
            raise ValueError("image_paths must include at least one base image path")

        with ExitStack() as stack:
            image_files = [stack.enter_context(open(path, "rb")) for path in image_paths]
            kwargs: dict[str, Any] = {
                "image": image_files,
                "prompt": prompt,
                **self._image_edit_options(size or "1024x1024"),
            }
            if mask_png_bytes:
                mask_file = stack.enter_context(NamedTemporaryFile(suffix=".png"))
                mask_file.write(mask_png_bytes)
                mask_file.flush()
                kwargs["mask"] = stack.enter_context(open(mask_file.name, "rb"))
            result = self.client.images.edit(**kwargs)

        image_bytes = self._extract_image_bytes(result)
        image = Image.open(BytesIO(image_bytes))
        stored = self.storage.save_bytes(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            category="generated",
            filename=f"edited-{brand_space_id}.png",
            content=image_bytes,
        )
        return {
            "mime_type": "image/png",
            "storage_path": stored.storage_path,
            "width": image.width,
            "height": image.height,
            "asset_role": "ai_image",
            "provider": self.provider_name,
            "model": self.settings.image_model,
            "size": size or "1024x1024",
        }
