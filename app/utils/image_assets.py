from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Iterator

from PIL import Image

try:
    import cairosvg
except Exception:  # noqa: BLE001
    cairosvg = None


def _looks_like_svg_bytes(content: bytes) -> bool:
    sample = content[:256].lstrip().lower()
    return sample.startswith(b"<svg") or b"<svg" in sample


def _svg_to_png_bytes(source: str | Path | bytes) -> bytes:
    if cairosvg is None:
        raise OSError("SVG support requires cairosvg to be installed.")
    if isinstance(source, (bytes, bytearray)):
        return cairosvg.svg2png(bytestring=bytes(source))
    return cairosvg.svg2png(url=str(source))


@contextmanager
def open_image_asset(source: str | Path | bytes | bytearray) -> Iterator[Image.Image]:
    if isinstance(source, (bytes, bytearray)):
        content = bytes(source)
        if _looks_like_svg_bytes(content):
            image = Image.open(BytesIO(_svg_to_png_bytes(content)))
        else:
            image = Image.open(BytesIO(content))
        try:
            yield image
        finally:
            image.close()
        return

    path = Path(source)
    if path.suffix.lower() == ".svg":
        image = Image.open(BytesIO(_svg_to_png_bytes(path)))
        try:
            yield image
        finally:
            image.close()
        return

    image = Image.open(path)
    try:
        yield image
    finally:
        image.close()
