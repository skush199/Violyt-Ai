from types import SimpleNamespace

from app.ai.providers.anthropic_provider import AnthropicTextProvider
from app.ai.providers.base import PromptEnvelope
from app.ai.providers.router import ProviderRouter


def test_provider_router_falls_back_when_preferred_provider_unavailable() -> None:
    router = ProviderRouter()
    router.settings.research_provider = "anthropic"
    router.settings.fallback_text_provider = "openai"
    anthropic_provider = router.text_providers["anthropic"]
    anthropic_provider.client = None
    selected = router.get_text_provider("research")
    assert selected.provider_name == "openai"


def test_provider_router_uses_mock_image_fallback_when_openai_image_unavailable() -> None:
    router = ProviderRouter()
    router.settings.image_provider = "openai"
    router.settings.fallback_image_provider = "mock"
    openai_provider = router.image_providers["openai"]
    openai_provider.client = None
    selected = router.get_image_provider()
    assert selected.provider_name == "mock"


def test_anthropic_provider_returns_fallback_when_model_call_fails() -> None:
    provider = AnthropicTextProvider()
    provider.client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **_: (_ for _ in ()).throw(RuntimeError("model not found"))
        )
    )

    fallback = "Use conservative brand guidance."
    result = provider.generate_text(
        PromptEnvelope(system="System prompt", user="User prompt"),
        fallback=fallback,
    )

    assert result == fallback
