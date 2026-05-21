#!/usr/bin/env python3
"""
Standalone GPT-4.1 Vision font detector.

Usage:
    python gpt41_font_detector.py path/to/image.png

Environment:
    OPENAI_API_KEY=...
    OPENAI_API_BASE=https://api.openai.com/v1   # optional
    OPENAI_FONT_MODEL=gpt-4.1                   # optional
"""

import argparse
import base64
import hashlib
import io
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageEnhance, ImageOps

try:
    from google.cloud import vision as google_cloud_vision
except ImportError:
    google_cloud_vision = None


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CACHE_VERSION = "2"
TRIGGER_PRINT_FORMATS = {".png", ".jpg", ".jpeg", ".webp"}


def load_local_env(env_file: Optional[Path] = None) -> None:
    """Load simple KEY=VALUE pairs from a local .env file into os.environ."""

    def normalize_env_value(key: str, value: str) -> str:
        normalized = value.strip().strip('"').strip("'")
        duplicated_prefix = f"{key}="
        if normalized.startswith(duplicated_prefix):
            logger.warning(
                "Detected malformed .env entry for %s. Stripping duplicated key prefix.",
                key,
            )
            normalized = normalized[len(duplicated_prefix) :].strip().strip('"').strip("'")
        return normalized

    if env_file is None:
        env_file = Path(__file__).with_name(".env")

    if not env_file.exists():
        return

    try:
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = normalize_env_value(key, value)

            if key and key not in os.environ:
                os.environ[key] = value
    except Exception as exc:
        logger.warning("Failed to load .env file %s: %s", env_file, exc)


def guess_image_mime_type(image_path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(image_path.suffix.lower(), "image/png")


def image_path_to_data_url(image_path: Path) -> str:
    mime_type = guess_image_mime_type(image_path)
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def pil_image_to_data_url(image: Image.Image, mime_type: str = "image/png") -> str:
    image_buffer = io.BytesIO()
    format_name = "PNG" if mime_type == "image/png" else "JPEG"
    image.save(image_buffer, format=format_name)
    encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def enhance_crop_for_typography(image: Image.Image, upscale: int = 2) -> Image.Image:
    """Create a higher-contrast crop that helps the vision model focus on letterforms."""
    grayscale = ImageOps.grayscale(image)
    autocontrast = ImageOps.autocontrast(grayscale)
    contrasted = ImageEnhance.Contrast(autocontrast).enhance(1.8)
    sharpened = ImageEnhance.Sharpness(contrasted).enhance(1.6)
    width, height = sharpened.size
    return sharpened.resize((width * upscale, height * upscale), Image.Resampling.LANCZOS)


def build_center_crop(image_path: Path) -> Optional[Image.Image]:
    """Create a center crop to help the model focus on typography."""
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return None

    width, height = image.size
    if width < 80 or height < 80:
        return image

    crop_width = int(width * 0.75)
    crop_height = int(height * 0.5)
    left = max(0, (width - crop_width) // 2)
    top = max(0, (height - crop_height) // 2)
    right = min(width, left + crop_width)
    bottom = min(height, top + crop_height)
    return image.crop((left, top, right, bottom))


def build_bottom_text_crop(image_path: Path) -> Optional[Image.Image]:
    """Create a crop that emphasizes lower text blocks common in posters and infographics."""
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return None

    width, height = image.size
    if width < 80 or height < 80:
        return image

    top = int(height * 0.45)
    bottom = min(height, int(height * 0.95))
    left = int(width * 0.06)
    right = min(width, int(width * 0.94))
    return image.crop((left, top, right, bottom))


def extract_google_ocr_context(image_path: Path) -> Optional[Dict[str, Any]]:
    """Use Google Vision OCR to find dominant text regions when available."""
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if google_cloud_vision is None or not credentials_path or not Path(credentials_path).exists():
        return None

    try:
        client = google_cloud_vision.ImageAnnotatorClient()
        with open(image_path, "rb") as image_file:
            response = client.document_text_detection(
                image=google_cloud_vision.Image(content=image_file.read())
            )

        if getattr(response, "error", None) and response.error.message:
            raise RuntimeError(response.error.message)

        regions = []
        full_text = getattr(response, "full_text_annotation", None)
        for page in getattr(full_text, "pages", []) or []:
            for block in getattr(page, "blocks", []) or []:
                words = []
                confidences = []
                vertices = []

                for paragraph in getattr(block, "paragraphs", []) or []:
                    for word in getattr(paragraph, "words", []) or []:
                        symbols = getattr(word, "symbols", []) or []
                        word_text = "".join(getattr(symbol, "text", "") for symbol in symbols).strip()
                        if word_text:
                            words.append(word_text)

                        word_confidence = getattr(word, "confidence", None)
                        if word_confidence is not None:
                            confidences.append(float(word_confidence))

                        bbox = getattr(word, "bounding_box", None)
                        for vertex in getattr(bbox, "vertices", []) or []:
                            x = getattr(vertex, "x", None)
                            y = getattr(vertex, "y", None)
                            if x is not None and y is not None:
                                vertices.append((int(x), int(y)))

                if words and vertices:
                    xs = [x for x, _ in vertices]
                    ys = [y for _, y in vertices]
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)
                    if max_x > min_x and max_y > min_y:
                        regions.append(
                            {
                                "text": " ".join(words),
                                "confidence": round(
                                    (sum(confidences) / len(confidences)) if confidences else 0.8,
                                    4,
                                ),
                                "bbox": (min_x, min_y, max_x - min_x, max_y - min_y),
                                "word_count": len(words),
                            }
                        )

        if not regions:
            return None

        best = max(regions, key=lambda item: item["confidence"])
        return {
            "text_sample": best["text"][:120],
            "text_blocks": len(regions),
            "ocr_regions": sorted(
                regions,
                key=lambda item: (item["bbox"][2] * item["bbox"][3]) + (item["confidence"] * 1000),
                reverse=True,
            )[:6],
        }
    except Exception as exc:
        logger.warning("Google OCR unavailable for standalone detector: %s", exc)
        return None


def build_ocr_crops(image_path: Path, ocr_context: Optional[Dict[str, Any]]) -> List[Image.Image]:
    """Create OCR-guided crops for the dominant text regions."""
    if not ocr_context or not ocr_context.get("ocr_regions"):
        return []

    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return []

    width, height = image.size
    crops: List[Image.Image] = []
    for region in ocr_context["ocr_regions"][:3]:
        x, y, w, h = region["bbox"]
        pad_x = max(8, int(w * 0.12))
        pad_y = max(8, int(h * 0.35))
        left = max(0, x - pad_x)
        top = max(0, y - pad_y)
        right = min(width, x + w + pad_x)
        bottom = min(height, y + h + pad_y)

        if right - left < 24 or bottom - top < 16:
            continue

        crops.append(image.crop((left, top, right, bottom)))

    return crops


def rank_ocr_regions(ocr_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank OCR regions by likelihood of being the dominant headline text."""
    if not ocr_context or not ocr_context.get("ocr_regions"):
        return []

    ranked: List[Tuple[float, Dict[str, Any]]] = []
    for region in ocr_context["ocr_regions"]:
        x, y, w, h = region.get("bbox", (0, 0, 0, 0))
        area = max(0, w) * max(0, h)
        confidence = float(region.get("confidence", 0.0) or 0.0)
        word_count = int(region.get("word_count", 0) or 0)
        text = str(region.get("text", "")).strip()

        # Prefer larger, cleaner, shorter headline-like regions over dense body copy.
        short_text_bonus = 1.25 if 1 <= word_count <= 8 else 0.9
        upper_page_bonus = 1.15 if y < 500 else 1.0
        height_bonus = 1.1 if h >= 24 else 0.95
        text_penalty = 0.85 if len(text) > 80 else 1.0

        score = area * short_text_bonus * upper_page_bonus * height_bonus * text_penalty
        score += confidence * 1500.0
        ranked.append((score, region))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [region for _, region in ranked]


def build_region_crop(image_path: Path, region: Dict[str, Any]) -> Optional[Image.Image]:
    """Crop a specific OCR region with padding."""
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return None

    width, height = image.size
    x, y, w, h = region.get("bbox", (0, 0, 0, 0))
    if w <= 0 or h <= 0:
        return None

    pad_x = max(8, int(w * 0.14))
    pad_y = max(8, int(h * 0.45))
    left = max(0, x - pad_x)
    top = max(0, y - pad_y)
    right = min(width, x + w + pad_x)
    bottom = min(height, y + h + pad_y)

    if right - left < 24 or bottom - top < 16:
        return None

    return image.crop((left, top, right, bottom))


def build_image_inputs(image_path: Path, ocr_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a richer set of images for the vision model: full image plus focused variants."""
    content: List[Dict[str, Any]] = [
        {
            "type": "input_image",
            "image_url": image_path_to_data_url(image_path),
            "detail": "high",
        }
    ]

    crops: List[Image.Image] = []
    center_crop = build_center_crop(image_path)
    bottom_crop = build_bottom_text_crop(image_path)
    if center_crop is not None:
        crops.append(center_crop)
    if bottom_crop is not None:
        crops.append(bottom_crop)
    crops.extend(build_ocr_crops(image_path, ocr_context))

    seen_sizes: set[Tuple[int, int]] = set()
    for crop in crops[:4]:
        if crop.size in seen_sizes:
            continue
        seen_sizes.add(crop.size)
        content.append(
            {
                "type": "input_image",
                "image_url": pil_image_to_data_url(crop, "image/png"),
                "detail": "high",
            }
        )
        content.append(
            {
                "type": "input_image",
                "image_url": pil_image_to_data_url(enhance_crop_for_typography(crop), "image/png"),
                "detail": "high",
            }
        )

    return content


def build_region_image_inputs(image_path: Path, region: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build focused image inputs for a single OCR region."""
    crop = build_region_crop(image_path, region)
    if crop is None:
        return []

    enhanced = enhance_crop_for_typography(crop)
    return [
        {
            "type": "input_image",
            "image_url": pil_image_to_data_url(crop, "image/png"),
            "detail": "high",
        },
        {
            "type": "input_image",
            "image_url": pil_image_to_data_url(enhanced, "image/png"),
            "detail": "high",
        },
    ]


def build_prompt(ocr_context: Optional[Dict[str, Any]], targeted: bool = False) -> str:
    ocr_lines = []
    if ocr_context:
        ocr_lines.append(f"OCR sample: {ocr_context.get('text_sample', '')}")
        for idx, region in enumerate(ocr_context.get("ocr_regions", [])[:3], start=1):
            ocr_lines.append(
                f"Region {idx}: text='{region.get('text', '')[:60]}', "
                f"confidence={region.get('confidence', 0)}, bbox={region.get('bbox')}"
            )

    ocr_summary = "\n".join(ocr_lines)
    task_focus = (
        "Focus especially on the dominant headline text and the largest OCR-guided crop. "
        "Prefer a close real family match over a generic label."
        if targeted
        else
        "Choose the dominant headline font rather than body text."
    )
    return (
        "Analyze the typography in these images and identify the most likely font "
        "used for the dominant headline or most visually prominent text. "
        "The first image is the full design. The remaining images are focused crops of "
        "the text regions and should be prioritized over the full image. "
        "Ignore logos, icons, and decorative elements. "
        f"{task_focus}\n"
        f"{ocr_summary}\n"
        "Return JSON only with keys: "
        "name, family, style, weight, is_bold, is_italic, confidence, explanation, top_candidates. "
        "Use a specific likely font name when possible. "
        "For family, prefer a real family name like 'Montserrat' or a close label "
        "like 'Montserrat-like' rather than only 'Serif' or 'Sans-Serif'. "
        "top_candidates must be an array of up to 3 short strings. "
        "Confidence must be a number from 0 to 1. "
        "If the text looks condensed, geometric, grotesk, humanist, serif, or slab-serif, mention that in explanation."
    )


def build_region_prompt(region: Dict[str, Any]) -> str:
    """Prompt specialized for one OCR text region."""
    return (
        "Analyze this cropped text region and identify the most likely font used in it. "
        "This crop is intended to isolate a single dominant text style. "
        "Ignore any nearby icons or logos. "
        f"OCR text for this crop: {region.get('text', '')[:120]}\n"
        "Return JSON only with keys: "
        "name, family, style, weight, is_bold, is_italic, confidence, explanation, top_candidates. "
        "Use a specific likely font name when possible. "
        "Prefer close family matches over generic labels."
    )


def extract_output_text(response_json: Dict[str, Any]) -> str:
    if response_json.get("output_text"):
        return response_json["output_text"]

    texts = []
    for item in response_json.get("output", []):
        for content in item.get("content", []):
            text_value = content.get("text")
            if text_value:
                texts.append(text_value)
    return "\n".join(texts)


def build_cache_key(image_path: Path, model: str, ocr_context: Optional[Dict[str, Any]]) -> str:
    hasher = hashlib.sha256()
    hasher.update(image_path.read_bytes())
    hasher.update(model.encode("utf-8"))
    hasher.update(CACHE_VERSION.encode("utf-8"))
    if ocr_context:
        hasher.update(json.dumps(ocr_context, sort_keys=True, default=str).encode("utf-8"))
    return hasher.hexdigest()


def load_cache(cache_path: Path) -> Dict[str, Any]:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache_path: Path, cache: Dict[str, Any]) -> None:
    try:
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not save cache %s: %s", cache_path, exc)


def normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and sanitize model output so repeated runs are more consistent."""
    normalized = dict(result)
    normalized["name"] = str(normalized.get("name", "Unknown")).strip() or "Unknown"
    normalized["family"] = str(normalized.get("family", "Unknown")).strip() or "Unknown"
    normalized["style"] = str(normalized.get("style", "Regular")).strip() or "Regular"
    normalized["weight"] = int(normalized.get("weight", 400) or 400)
    normalized["is_bold"] = bool(normalized.get("is_bold", False))
    normalized["is_italic"] = bool(normalized.get("is_italic", False))
    confidence = float(normalized.get("confidence", 0.0) or 0.0)
    normalized["confidence"] = max(0.0, min(1.0, confidence))
    explanation = str(normalized.get("explanation", "")).strip()
    normalized["explanation"] = explanation

    top_candidates = normalized.get("top_candidates", [])
    if not isinstance(top_candidates, list):
        top_candidates = []
    normalized["top_candidates"] = [str(item).strip() for item in top_candidates[:3] if str(item).strip()]
    return normalized


def canonicalize_label(label: str) -> str:
    """Normalize font labels so close variants collapse into one bucket."""
    text = " ".join(str(label).strip().lower().replace("_", " ").split())
    replacements = {
        "sans serif": "sans-serif",
        "semi bold": "semibold",
        "extra bold": "extrabold",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def build_result_bucket_key(result: Dict[str, Any]) -> str:
    family = canonicalize_label(result.get("family", "unknown"))
    name = canonicalize_label(result.get("name", "unknown"))
    style = canonicalize_label(result.get("style", "regular"))
    return f"{family}|{name}|{style}"


def aggregate_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine multiple model passes into one more stable final answer."""
    if not results:
        raise RuntimeError("No results available to aggregate.")

    buckets: Dict[str, Dict[str, Any]] = {}
    for index, result in enumerate(results):
        bucket_key = build_result_bucket_key(result)
        confidence = float(result.get("confidence", 0.0) or 0.0)
        pass_weight = 1.0 if index == 0 else 0.85
        weighted_confidence = confidence * pass_weight

        if bucket_key not in buckets:
            buckets[bucket_key] = {
                "result": result,
                "score": 0.0,
                "count": 0,
                "top_candidates": [],
            }

        buckets[bucket_key]["score"] += weighted_confidence
        buckets[bucket_key]["count"] += 1
        buckets[bucket_key]["top_candidates"].extend(result.get("top_candidates", []))

    best_bucket = max(
        buckets.values(),
        key=lambda item: (item["score"], item["count"], item["result"].get("confidence", 0.0)),
    )
    final_result = dict(best_bucket["result"])
    final_result["confidence"] = max(
        float(final_result.get("confidence", 0.0) or 0.0),
        min(0.99, best_bucket["score"] / max(1, best_bucket["count"])),
    )

    seen_candidates = []
    for candidate in best_bucket["top_candidates"]:
        if candidate and candidate not in seen_candidates:
            seen_candidates.append(candidate)
    if seen_candidates:
        final_result["top_candidates"] = seen_candidates[:3]

    final_result["explanation"] = (
        f"{final_result.get('explanation', '').strip()} "
        f"[Consensus from {best_bucket['count']} agreeing pass(es).]"
    ).strip()
    return final_result


def is_generic_result(result: Dict[str, Any]) -> bool:
    """Detect weak or generic responses that deserve a second targeted pass."""
    name = str(result.get("name", "")).strip().lower()
    family = str(result.get("family", "")).strip().lower()
    confidence = float(result.get("confidence", 0.0) or 0.0)

    generic_names = {
        "unknown",
        "unknown font",
        "unknown_font",
        "text_detected_from_image",
        "serif",
        "sans-serif",
        "sans serif",
    }
    generic_families = {"unknown", "serif", "sans-serif", "sans serif"}
    return (
        confidence < 0.72
        or name in generic_names
        or family in generic_families
        or name.endswith("-like") is False and family in generic_families
    )


def is_region_result_useful(result: Dict[str, Any]) -> bool:
    """Decide whether a per-region result is strong enough to contribute to consensus."""
    if is_generic_result(result):
        return False
    return float(result.get("confidence", 0.0) or 0.0) >= 0.68


def make_openai_request(
    api_key: str,
    api_base: str,
    model: str,
    content: List[Dict[str, Any]],
    prompt: str,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}, *content]}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "font_detection_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "family": {"type": "string"},
                        "style": {"type": "string"},
                        "weight": {"type": "integer"},
                        "is_bold": {"type": "boolean"},
                        "is_italic": {"type": "boolean"},
                        "confidence": {"type": "number"},
                        "explanation": {"type": "string"},
                        "top_candidates": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 3,
                        },
                    },
                    "required": [
                        "name",
                        "family",
                        "style",
                        "weight",
                        "is_bold",
                        "is_italic",
                        "confidence",
                        "explanation",
                        "top_candidates",
                    ],
                },
            }
        },
        "max_output_tokens": 250,
    }

    response = requests.post(
        f"{api_base}/responses",
        headers=headers,
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    result = response.json()
    output_text = extract_output_text(result)
    return normalize_result(json.loads(output_text))


def call_openai_font_detection(image_path: Path) -> Dict[str, Any]:
    if image_path.suffix.lower() in TRIGGER_PRINT_FORMATS:
        print("gpt41_font_detector.py should use this file", flush=True)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_FONT_MODEL", "gpt-4.1").strip()
    cache_path = image_path.with_name("gpt41_font_detector_cache.json")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    ocr_context = extract_google_ocr_context(image_path)
    cache = load_cache(cache_path)
    cache_key = build_cache_key(image_path, model, ocr_context)
    if cache_key in cache:
        return cache[cache_key]

    all_results: List[Dict[str, Any]] = []
    ranked_regions = rank_ocr_regions(ocr_context)

    # Prefer analyzing strong OCR regions first; this reduces confusion from full layouts.
    for region in ranked_regions[:3]:
        region_inputs = build_region_image_inputs(image_path, region)
        if not region_inputs:
            continue
        region_result = make_openai_request(
            api_key=api_key,
            api_base=api_base,
            model=model,
            content=region_inputs,
            prompt=build_region_prompt(region),
        )
        if is_region_result_useful(region_result):
            all_results.append(region_result)

    # If region-only analysis is weak or unavailable, use the richer full-layout pass.
    if not all_results:
        content = build_image_inputs(image_path, ocr_context)
        parsed = make_openai_request(
            api_key=api_key,
            api_base=api_base,
            model=model,
            content=content,
            prompt=build_prompt(ocr_context, targeted=False),
        )
        all_results.append(parsed)

        if is_generic_result(parsed):
            targeted_result = make_openai_request(
                api_key=api_key,
                api_base=api_base,
                model=model,
                content=content[:3],
                prompt=build_prompt(ocr_context, targeted=True),
            )
            all_results.append(targeted_result)
    else:
        # Add one full-layout pass as a weaker tie-breaker after region analysis.
        content = build_image_inputs(image_path, ocr_context)
        layout_result = make_openai_request(
            api_key=api_key,
            api_base=api_base,
            model=model,
            content=content[:3],
            prompt=build_prompt(ocr_context, targeted=True),
        )
        all_results.append(layout_result)

    parsed = aggregate_results(all_results)

    cache[cache_key] = parsed
    save_cache(cache_path, cache)
    return parsed


def print_result(result: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("GPT-4.1 FONT DETECTION")
    print("=" * 60)
    print(f"Name: {result.get('name', 'Unknown')}")
    print(f"Family: {result.get('family', 'Unknown')}")
    print(f"Style: {result.get('style', 'Unknown')}")
    print(f"Weight: {result.get('weight', 400)}")
    print(f"Bold: {result.get('is_bold', False)}")
    print(f"Italic: {result.get('is_italic', False)}")
    print(f"Confidence: {float(result.get('confidence', 0.0)):.2%}")
    if result.get("top_candidates"):
        print(f"Top Candidates: {', '.join(result.get('top_candidates', []))}")
    print(f"Explanation: {result.get('explanation', '')}")
    print("=" * 60)


def main() -> int:
    load_local_env()

    parser = argparse.ArgumentParser(
        description="Detect font name/family from an image using GPT-4.1 vision."
    )
    parser.add_argument("image", help="Path to the image file")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        logger.error("Image file not found: %s", image_path)
        return 1

    try:
        result = call_openai_font_detection(image_path)
        print_result(result)
        return 0
    except requests.HTTPError as exc:
        logger.error("OpenAI API HTTP error: %s", exc)
        try:
            logger.error("Response body: %s", exc.response.text)
        except Exception:
            pass
        return 1
    except Exception as exc:
        logger.error("Font detection failed: %s", exc)
        return 1
if __name__ == "__main__":
    raise SystemExit(main())
