from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from app.ai.providers.image_generation import ImageGenerationProvider


def _masked_box_bytes(size: tuple[int, int], box: tuple[int, int, int, int]) -> bytes:
    mask = Image.new("RGBA", size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)
    draw.rectangle(box, fill=(0, 0, 0, 0))
    buffer = BytesIO()
    mask.save(buffer, format="PNG")
    return buffer.getvalue()


def test_mock_image_provider_edit_strips_logo_background_before_overlay(tmp_path: Path) -> None:
    provider = ImageGenerationProvider()
    base_path = tmp_path / "base.png"
    logo_path = tmp_path / "logo.png"

    Image.new("RGBA", (220, 120), (32, 44, 60, 255)).save(base_path)
    logo = Image.new("RGBA", (200, 100), (255, 255, 255, 255))
    logo_draw = ImageDraw.Draw(logo)
    logo_draw.rounded_rectangle((48, 20, 152, 80), radius=16, fill=(0, 57, 117, 255))
    logo.save(logo_path)

    stored: dict[str, bytes] = {}

    def save_bytes(tenant_id, brand_space_id, category, filename, content):
        stored["content"] = content
        return SimpleNamespace(storage_path="tenant/brand/generated/edited.png")

    provider.storage = SimpleNamespace(save_bytes=save_bytes)
    asset = provider.edit(
        "tenant",
        "brand",
        "Place the real logo",
        image_paths=[str(base_path), str(logo_path)],
        size="1024x1024",
        mask_png_bytes=_masked_box_bytes((220, 120), (100, 24, 199, 73)),
    )

    output = Image.open(BytesIO(stored["content"])).convert("RGBA")

    assert asset["storage_path"] == "tenant/brand/generated/edited.png"
    assert output.getpixel((110, 48))[:3] == (0, 57, 117)
