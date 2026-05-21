from __future__ import annotations

import hashlib
from io import BytesIO
from uuid import UUID

from PIL import Image, ImageDraw, ImageOps

from app.ai.providers.base import ImageGenerationBackend
from app.core.config import get_settings
from app.integrations.object_storage import LocalObjectStorage
from app.utils.image_assets import open_image_asset


class ImageGenerationProvider(ImageGenerationBackend):
    provider_name = "mock"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = LocalObjectStorage()

    def generate(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        prompt: str,
        size: str | None = None,
    ) -> dict:
        size_map = {
            "1024x1024": (1400, 1400),
            "1536x1024": (1600, 1067),
            "1024x1536": (1067, 1600),
        }
        width, height = size_map.get(size or "1024x1024", (1400, 1400))
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()
        primary = (24, 78, 154)
        secondary = (243, 156, 18)
        accent = (
            80 + digest[0] % 120,
            80 + digest[1] % 120,
            80 + digest[2] % 120,
        )
        img = Image.new("RGB", (width, height), color=(247, 244, 236))
        draw = ImageDraw.Draw(img)
        soft_primary = tuple(int((247 + channel) / 2) for channel in primary)
        soft_secondary = tuple(int((247 + channel) / 2) for channel in secondary)
        variant = digest[4] % 3

        draw.rounded_rectangle((int(width * 0.05), int(height * 0.05), int(width * 0.95), int(height * 0.95)), radius=60, fill=(252, 249, 242), outline=soft_primary, width=6)
        draw.ellipse((int(width * 0.13), int(height * 0.09), int(width * 0.54), int(height * 0.5)), fill=soft_secondary)
        draw.ellipse((int(width * 0.59), int(height * 0.16), int(width * 0.84), int(height * 0.41)), fill=tuple(int((247 + channel) / 2) for channel in accent))

        if variant == 0:
            draw.rounded_rectangle((int(width * 0.15), int(height * 0.56), int(width * 0.23), int(height * 0.77)), radius=26, fill=primary)
            draw.rounded_rectangle((int(width * 0.26), int(height * 0.49), int(width * 0.35), int(height * 0.77)), radius=26, fill=soft_primary)
            draw.rounded_rectangle((int(width * 0.38), int(height * 0.42), int(width * 0.47), int(height * 0.77)), radius=26, fill=primary)
            line_points = [
                (int(width * 0.18), int(height * 0.67)),
                (int(width * 0.32), int(height * 0.59)),
                (int(width * 0.42), int(height * 0.5)),
                (int(width * 0.64), int(height * 0.37)),
                (int(width * 0.79), int(height * 0.24)),
            ]
        elif variant == 1:
            draw.ellipse((int(width * 0.18), int(height * 0.53), int(width * 0.35), int(height * 0.71)), fill=primary)
            draw.rounded_rectangle((int(width * 0.39), int(height * 0.54), int(width * 0.73), int(height * 0.68)), radius=36, fill=soft_primary)
            draw.rounded_rectangle((int(width * 0.23), int(height * 0.74), int(width * 0.7), int(height * 0.8)), radius=30, fill=secondary)
            line_points = [
                (int(width * 0.2), int(height * 0.61)),
                (int(width * 0.32), int(height * 0.51)),
                (int(width * 0.46), int(height * 0.58)),
                (int(width * 0.63), int(height * 0.43)),
                (int(width * 0.78), int(height * 0.28)),
            ]
        else:
            draw.rounded_rectangle((int(width * 0.17), int(height * 0.55), int(width * 0.81), int(height * 0.76)), radius=42, fill=soft_primary)
            draw.ellipse((int(width * 0.59), int(height * 0.49), int(width * 0.79), int(height * 0.69)), fill=secondary)
            draw.rounded_rectangle((int(width * 0.23), int(height * 0.44), int(width * 0.37), int(height * 0.82)), radius=30, fill=primary)
            line_points = [
                (int(width * 0.2), int(height * 0.69)),
                (int(width * 0.34), int(height * 0.58)),
                (int(width * 0.49), int(height * 0.61)),
                (int(width * 0.67), int(height * 0.4)),
                (int(width * 0.82), int(height * 0.25)),
            ]

        draw.line(line_points, fill=primary, width=36, joint="curve")
        tip_x, tip_y = line_points[-1]
        draw.polygon(
            [
                (tip_x, tip_y),
                (tip_x - 90, tip_y + 46),
                (tip_x - 36, tip_y - 108),
            ],
            fill=primary,
        )

        draw.rounded_rectangle((int(width * 0.13), int(height * 0.12), int(width * 0.48), int(height * 0.19)), radius=26, fill=(255, 255, 255), outline=soft_primary, width=4)
        draw.rounded_rectangle((int(width * 0.13), int(height * 0.22), int(width * 0.44), int(height * 0.27)), radius=22, fill=(255, 255, 255), outline=soft_secondary, width=3)
        draw.rounded_rectangle((int(width * 0.13), int(height * 0.3), int(width * 0.4), int(height * 0.35)), radius=22, fill=(255, 255, 255), outline=soft_secondary, width=3)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        filename = f"generated-{brand_space_id}.png"
        stored = self.storage.save_bytes(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            category="generated",
            filename=filename,
            content=buffer.getvalue(),
        )
        return {
            "mime_type": "image/png",
            "storage_path": stored.storage_path,
            "width": width,
            "height": height,
            "asset_role": "ai_image",
            "provider": self.provider_name,
            "size": size or "1024x1024",
        }

    @staticmethod
    def _edge_background_should_strip(image: Image.Image, threshold: int = 245) -> bool:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        if width <= 0 or height <= 0:
            return False
        edge_pixels: list[tuple[int, int, int, int]] = []
        pixels = rgba.load()
        for x in range(width):
            edge_pixels.append(pixels[x, 0])
            edge_pixels.append(pixels[x, height - 1])
        for y in range(1, max(height - 1, 1)):
            edge_pixels.append(pixels[0, y])
            edge_pixels.append(pixels[width - 1, y])
        opaque_edges = [pixel for pixel in edge_pixels if pixel[3] > 0]
        if not opaque_edges:
            return False
        light_edges = [
            pixel
            for pixel in opaque_edges
            if pixel[0] >= threshold and pixel[1] >= threshold and pixel[2] >= threshold
        ]
        return (len(light_edges) / len(opaque_edges)) >= 0.75

    @classmethod
    def _strip_logo_background_if_safe(cls, image: Image.Image) -> Image.Image:
        rgba = image.convert("RGBA")
        if not cls._edge_background_should_strip(rgba):
            return rgba
        width, height = rgba.size
        pixels = rgba.load()
        keep = [[True for _ in range(width)] for _ in range(height)]
        queue: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()

        def is_background(px: tuple[int, int, int, int]) -> bool:
            red, green, blue, alpha = px
            return alpha > 0 and red >= 245 and green >= 245 and blue >= 245

        for x in range(width):
            queue.append((x, 0))
            queue.append((x, height - 1))
        for y in range(height):
            queue.append((0, y))
            queue.append((width - 1, y))

        while queue:
            x, y = queue.pop()
            if (x, y) in seen or x < 0 or y < 0 or x >= width or y >= height:
                continue
            seen.add((x, y))
            if not is_background(pixels[x, y]):
                continue
            keep[y][x] = False
            queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))

        cleaned = rgba.copy()
        cleaned_pixels = cleaned.load()
        for y in range(height):
            for x in range(width):
                if not keep[y][x]:
                    red, green, blue, _alpha = cleaned_pixels[x, y]
                    cleaned_pixels[x, y] = (red, green, blue, 0)
        return cleaned

    @staticmethod
    def _trim_transparent_logo_margins(image: Image.Image) -> Image.Image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        if not bbox:
            return rgba
        left, top, right, bottom = bbox
        if left == 0 and top == 0 and right == rgba.width and bottom == rgba.height:
            return rgba
        return rgba.crop(bbox)

    def edit(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        prompt: str,
        image_paths: list[str],
        size: str | None = None,
        mask_png_bytes: bytes | None = None,
    ) -> dict:
        if not image_paths:
            raise ValueError("image_paths must include at least one base image path")
        with open_image_asset(image_paths[0]) as opened_base:
            base_image = opened_base.convert("RGBA")
        composite = base_image.copy()

        if mask_png_bytes and len(image_paths) > 1:
            try:
                with open_image_asset(image_paths[1]) as opened_logo:
                    logo_image = self._trim_transparent_logo_margins(
                        self._strip_logo_background_if_safe(opened_logo.convert("RGBA"))
                    )
                target_box = None
                mask = Image.open(BytesIO(mask_png_bytes)).convert("RGBA")
                alpha = mask.getchannel("A")
                transparent_bbox = alpha.point(lambda px: 255 if px == 0 else 0).getbbox()
                if transparent_bbox:
                    target_box = transparent_bbox
                if target_box is None:
                    width, height = composite.size
                    target_box = (
                        int(width * 0.76),
                        int(height * 0.06),
                        int(width * 0.94),
                        int(height * 0.16),
                    )

                left, top, right, bottom = target_box
                target_width = max(right - left, 1)
                target_height = max(bottom - top, 1)
                contained = ImageOps.contain(
                    logo_image,
                    (target_width, target_height),
                    method=Image.Resampling.LANCZOS,
                )
                paste_x = left + max((target_width - contained.width) // 2, 0)
                paste_y = top + max((target_height - contained.height) // 2, 0)
                composite.alpha_composite(contained, dest=(paste_x, paste_y))
            except Exception:
                pass
        elif len(image_paths) > 1:
            width, height = composite.size
            card_specs = [
                (0.58, 0.12, 0.3, 0.3),
                (0.08, 0.58, 0.24, 0.22),
                (0.68, 0.62, 0.18, 0.18),
            ]
            for index, image_path in enumerate(image_paths[1:4]):
                try:
                    with open_image_asset(image_path) as opened_reference:
                        reference_image = opened_reference.convert("RGBA")
                except Exception:
                    continue
                spec = card_specs[min(index, len(card_specs) - 1)]
                left = int(width * spec[0])
                top = int(height * spec[1])
                card_width = max(int(width * spec[2]), 1)
                card_height = max(int(height * spec[3]), 1)
                frame = Image.new("RGBA", (card_width, card_height), (255, 255, 255, 245))
                framed = reference_image.copy()
                framed.thumbnail((max(card_width - 24, 1), max(card_height - 24, 1)))
                paste_x = max((card_width - framed.width) // 2, 0)
                paste_y = max((card_height - framed.height) // 2, 0)
                frame.alpha_composite(framed, dest=(paste_x, paste_y))
                composite.alpha_composite(frame, dest=(left, top))

        output = composite.convert("RGB")
        buffer = BytesIO()
        output.save(buffer, format="PNG")
        stored = self.storage.save_bytes(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            category="generated",
            filename=f"edited-{brand_space_id}.png",
            content=buffer.getvalue(),
        )
        return {
            "mime_type": "image/png",
            "storage_path": stored.storage_path,
            "width": output.width,
            "height": output.height,
            "asset_role": "ai_image",
            "provider": self.provider_name,
            "size": size or "1024x1024",
        }
