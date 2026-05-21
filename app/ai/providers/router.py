from __future__ import annotations

from app.ai.providers.anthropic_provider import AnthropicTextProvider
from app.ai.providers.base import ImageGenerationBackend, TextGenerationProvider
from app.ai.providers.image_generation import ImageGenerationProvider
from app.ai.providers.openai_provider import OpenAIImageProvider, OpenAITextProvider
from app.core.config import get_settings


class ProviderRouter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.text_providers: dict[str, TextGenerationProvider] = {
            "openai": OpenAITextProvider(),
            "anthropic": AnthropicTextProvider(),
        }
        self.image_providers: dict[str, ImageGenerationBackend] = {
            "openai": OpenAIImageProvider(),
            "mock": ImageGenerationProvider(),
        }

    def get_text_provider(self, purpose: str) -> TextGenerationProvider:
        preferred = self.settings.research_provider if purpose == "research" else self.settings.text_provider
        fallback = self.settings.fallback_text_provider
        provider = self.text_providers.get(preferred)
        if provider and getattr(provider, "client", True):
            return provider
        return self.text_providers[fallback]

    def get_image_provider(self) -> ImageGenerationBackend:
        preferred = self.image_providers.get(self.settings.image_provider)
        if preferred and getattr(preferred, "client", True):
            return preferred
        return self.image_providers[self.settings.fallback_image_provider]
