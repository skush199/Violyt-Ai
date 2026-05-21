from io import BytesIO
from types import SimpleNamespace
import base64

from PIL import Image

from app.ai.providers.openai_provider import OpenAIImageProvider


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color=(12, 34, 56)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_openai_image_provider_generate_omits_response_format() -> None:
    provider = OpenAIImageProvider()
    calls: list[dict] = []
    provider.client = SimpleNamespace(
        images=SimpleNamespace(
            generate=lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
                data=[SimpleNamespace(b64_json=base64.b64encode(_png_bytes()).decode("ascii"))]
            )
        )
    )
    provider.storage = SimpleNamespace(
        save_bytes=lambda tenant_id, brand_space_id, category, filename, content: SimpleNamespace(storage_path="tenant/brand/generated/test.png")
    )

    asset = provider.generate("tenant", "brand", "Prompt", size="1024x1024")

    assert "response_format" not in calls[0]
    assert asset["storage_path"] == "tenant/brand/generated/test.png"
    assert asset["width"] == 8
    assert asset["height"] == 8


def test_openai_image_provider_extracts_image_from_url_when_base64_missing(monkeypatch) -> None:
    provider = OpenAIImageProvider()
    provider.client = None

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return _png_bytes()

    monkeypatch.setattr(
        "app.ai.providers.openai_provider.urlopen",
        lambda url, timeout=120: _Response(),
    )

    image_bytes = provider._extract_image_bytes(SimpleNamespace(data=[SimpleNamespace(url="https://example.com/image.png")]))

    assert image_bytes.startswith(b"\x89PNG")


def test_openai_image_provider_edit_omits_input_fidelity_for_mini_model() -> None:
    provider = OpenAIImageProvider()
    provider.settings.image_model = "gpt-image-1-mini"
    calls: list[dict] = []
    provider.client = SimpleNamespace(
        images=SimpleNamespace(
            edit=lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
                data=[SimpleNamespace(b64_json=base64.b64encode(_png_bytes()).decode("ascii"))]
            )
        )
    )
    provider.storage = SimpleNamespace(
        save_bytes=lambda tenant_id, brand_space_id, category, filename, content: SimpleNamespace(storage_path="tenant/brand/generated/test.png")
    )

    asset = provider.edit("tenant", "brand", "Place the real logo", image_paths=[__file__], size="1024x1024")

    assert "input_fidelity" not in calls[0]
    assert "quality" not in calls[0]
    assert asset["storage_path"] == "tenant/brand/generated/test.png"
