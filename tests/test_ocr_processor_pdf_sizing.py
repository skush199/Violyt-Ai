from __future__ import annotations

import io

from PIL import Image

from ocr_processor import GoogleVisionOCRProcessor


class _FakePageImage:
    def __init__(self, image: Image.Image) -> None:
        self.annotated = image
        self.original = image


class _FakePage:
    def __init__(self, image: Image.Image) -> None:
        self._image = image

    def to_image(self, resolution: int = 300) -> _FakePageImage:
        return _FakePageImage(self._image)


def test_resize_image_to_limits_caps_max_dimension() -> None:
    processor = GoogleVisionOCRProcessor()
    image = Image.new("RGB", (12000, 6000), color="white")

    resized, meta = processor._resize_image_to_limits(
        image,
        max_dimension=8000,
        max_total_pixels=25_000_000,
    )

    assert meta["resized"] is True
    assert meta["original_size"] == (12000, 6000)
    assert max(resized.size) <= 8000
    assert resized.width * resized.height <= 25_000_000


def test_render_pdf_page_for_ocr_outputs_jpeg_bytes_under_caps() -> None:
    processor = GoogleVisionOCRProcessor()
    page = _FakePage(Image.new("RGB", (13334, 7500), color="white"))

    payload, meta = processor._render_pdf_page_for_ocr(page)

    assert meta["resized"] is True
    assert meta["original_size"] == (13334, 7500)
    assert max(meta["final_size"]) <= processor.PDF_OCR_MAX_DIMENSION_PX
    assert meta["final_size"][0] * meta["final_size"][1] <= processor.PDF_OCR_MAX_TOTAL_PIXELS
    assert meta["format"] == "JPEG"
    assert payload[:2] == b"\xff\xd8"

    rendered = Image.open(io.BytesIO(payload))
    assert rendered.size == meta["final_size"]
