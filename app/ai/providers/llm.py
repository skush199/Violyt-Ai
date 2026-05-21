from app.ai.providers.base import PromptEnvelope
from app.ai.providers.openai_provider import OpenAITextProvider


LLMProvider = OpenAITextProvider

__all__ = ["PromptEnvelope", "LLMProvider"]
