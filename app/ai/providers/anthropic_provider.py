from __future__ import annotations

import json
import logging
from typing import Any

from app.ai.providers.base import PromptEnvelope, TextGenerationProvider
from app.core.config import get_settings


logger = logging.getLogger(__name__)


class AnthropicTextProvider(TextGenerationProvider):
    provider_name = "anthropic"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = None
        if self.settings.anthropic_api_key:
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=self.settings.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self.client = None

    def generate_structured_json(self, envelope: PromptEnvelope, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.client:
            return fallback
        try:
            response = self.client.messages.create(
                model=self.settings.anthropic_model,
                system=envelope.system,
                max_tokens=1200,
                messages=[{"role": "user", "content": f"{envelope.user}\n\nReturn JSON only."}],
            )
            text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Anthropic structured generation failed, using fallback: %s", exc)
            return fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback

    def generate_text(self, envelope: PromptEnvelope, fallback: str) -> str:
        if not self.client:
            return fallback
        try:
            response = self.client.messages.create(
                model=self.settings.anthropic_model,
                system=envelope.system,
                max_tokens=1200,
                messages=[{"role": "user", "content": envelope.user}],
            )
            text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Anthropic text generation failed, using fallback: %s", exc)
            return fallback
        return text or fallback
