#!/usr/bin/env python3
"""
Format Validation & Conversion Module
=======================================
Provides magic byte detection, format validation, and conversion utilities
for handling various file formats in the font detector.

Features:
- Magic byte (file signature) based format detection
- Format conversion for unsupported image types
- Multi-page image handling
- 16-bit image conversion to 8-bit

Author: AI Assistant
License: MIT
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class ImageFormat(Enum):
    """Supported image formats."""

    PNG = "png"
    JPEG = "jpeg"
    GIF = "gif"
    BMP = "bmp"
    TIFF = "tiff"
    WEBP = "webp"
    SVG = "svg"
    HEIC = "heic"
    AVIF = "avif"
    ICO = "ico"
    PSD = "psd"
    PDF = "pdf"
    EPS = "eps"
    UNKNOWN = "unknown"


class DocumentFormat(Enum):
    """Supported document formats."""

    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    PPTX = "pptx"
    PPT = "ppt"
    ODT = "odt"
    RTF = "rtf"
    UNKNOWN = "unknown"


class FontFormat(Enum):
    """Supported font formats."""

    TTF = "ttf"
    OTF = "otf"
    WOFF = "woff"
    WOFF2 = "woff2"
    EOT = "eot"
    UNKNOWN = "unknown"


MAGIC_BYTES: Dict[str, bytes] = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "gif87a": b"GIF87a",
    "gif89a": b"GIF89a",
    "bmp": b"BM",
    "tiff_le": b"II\x2a\x00",
    "tiff_be": b"MM\x00\x2a",
    "webp": b"RIFF",
    "pdf": b"%PDF",
    "eps": b"\xc5\xd0\xd3\xc6",
    "psd": b"8BPS",
    "zip": b"PK\x03\x04",
    "odt": b"PK\x03\x04",
    "ttf": b"\x00\x01\x00\x00",
    "otf": b"OTTO",
    "woff": b"wOFF",
    "woff2": b"wOF2",
    "eot": b"\x84\x00\x00\x00",
    "heic": b"\x00\x00\x00\x18ftyp",
    "avif": b"\x00\x00\x00\x20ftyp",
}

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".webp",
    ".svg",
    ".heic",
    ".avif",
    ".ico",
    ".psd",
}
SUPPORTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".odt",
    ".rtf",
}
SUPPORTED_FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2", ".eot"}

CONVERTIBLE_TO_PNG = {".svg", ".heic", ".avif", ".psd", ".eps"}
NEEDS_MULTI_PAGE_HANDLING = {".gif", ".tiff", ".pdf"}
REQUIRES_8BIT_CONVERSION = {"tiff", "bmp"}


@dataclass
class FormatInfo:
    """Information about a file's format."""

    detected_format: str
    confidence: float
    extension: str
    mime_type: str
    is_supported: bool
    needs_conversion: bool
    conversion_needed: Optional[str] = None
    warning: Optional[str] = None


def detect_format_by_magic(file_path: Union[str, Path]) -> Tuple[str, float]:
    """Detect file format by reading magic bytes.

    Args:
        file_path: Path to the file

    Returns:
        Tuple of (format_name, confidence_score)
    """
    file_path = Path(file_path)

    try:
        with open(file_path, "rb") as f:
            header = f.read(16)

        if len(header) < 4:
            return "unknown", 0.0

        for format_name, magic in MAGIC_BYTES.items():
            if header.startswith(magic):
                if format_name == "zip":
                    detected_zip_format = _detect_zip_based_document_format(file_path)
                    if detected_zip_format:
                        return detected_zip_format, 0.95
                return format_name, 1.0

        if header.startswith(b"<"):
            if header.startswith(b"<svg", 0, 4) or b"<svg" in header[:1024].decode(
                "utf-8", errors="ignore"
            ):
                return "svg", 0.9

        if b"{\\rtf" in header or header.startswith(b"{\\rtf"):
            return "rtf", 0.9

        return "unknown", 0.0

    except Exception as e:
        logger.debug(f"Error reading magic bytes: {e}")
        return "unknown", 0.0


def _detect_zip_based_document_format(file_path: Path) -> Optional[str]:
    """Infer actual Office/OpenDocument format from a ZIP container."""
    try:
        with zipfile.ZipFile(file_path, "r") as archive:
            names = set(archive.namelist())
    except Exception as e:
        logger.debug(f"Error inspecting zip container {file_path}: {e}")
        return None

    if any(name.startswith("ppt/") for name in names):
        return "pptx"
    if any(name.startswith("word/") for name in names):
        return "docx"
    if "mimetype" in names and any(name.startswith("content.xml") for name in names):
        return "odt"

    return None


def validate_image_format(
    file_path: Union[str, Path], strict: bool = False
) -> FormatInfo:
    """Validate and detect image format with magic byte verification.

    Args:
        file_path: Path to the image file
        strict: If True, require magic byte match with extension

    Returns:
        FormatInfo with validation details
    """
    file_path = Path(file_path)
    extension = file_path.suffix.lower()
    magic_format, magic_confidence = detect_format_by_magic(file_path)

    result = FormatInfo(
        detected_format=magic_format,
        confidence=magic_confidence,
        extension=extension,
        mime_type="",
        is_supported=False,
        needs_conversion=False,
    )

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".heic": "image/heic",
        ".avif": "image/avif",
        ".ico": "image/x-icon",
        ".psd": "image/vnd.adobe.photoshop",
        ".eps": "application/eps",
        ".pdf": "application/pdf",
    }
    result.mime_type = mime_types.get(extension, "application/octet-stream")

    if extension in SUPPORTED_IMAGE_EXTENSIONS:
        result.is_supported = True

        if extension == ".svg" and magic_format != "unknown":
            result.needs_conversion = True
            result.conversion_needed = "png"
            result.detected_format = "svg"
        elif extension == ".heic":
            result.needs_conversion = True
            result.conversion_needed = "png"
            result.detected_format = "heic"
        elif extension == ".avif":
            result.needs_conversion = True
            result.conversion_needed = "png"
            result.detected_format = "avif"
        elif extension == ".psd":
            result.needs_conversion = True
            result.conversion_needed = "png"
            result.detected_format = "psd"
        elif extension == ".eps":
            result.needs_conversion = True
            result.conversion_needed = "png"
            result.detected_format = "eps"

    if strict and extension:
        if not result.is_supported:
            result.warning = f"Extension {extension} is not in supported list"
        elif magic_confidence > 0 and magic_format != extension.lstrip("."):
            if magic_format not in ["tiff_le", "tiff_be"] or extension not in [
                ".tiff",
                ".tif",
            ]:
                result.warning = f"Extension ({extension}) doesn't match magic bytes ({magic_format})"

    return result


def validate_document_format(file_path: Union[str, Path]) -> FormatInfo:
    """Validate document format.

    Args:
        file_path: Path to the document file

    Returns:
        FormatInfo with validation details
    """
    file_path = Path(file_path)
    extension = file_path.suffix.lower()
    magic_format, magic_confidence = detect_format_by_magic(file_path)

    result = FormatInfo(
        detected_format=magic_format,
        confidence=magic_confidence,
        extension=extension,
        mime_type="application/octet-stream",
        is_supported=False,
        needs_conversion=False,
    )

    if extension in SUPPORTED_DOCUMENT_EXTENSIONS:
        result.is_supported = True

        if magic_format in {"docx", "pptx", "odt"} and magic_format != extension.lstrip("."):
            result.warning = (
                f"Extension ({extension}) does not match document contents ({magic_format}). "
                f"Using detected {magic_format} structure."
            )

        elif extension == ".doc":
            result.warning = (
                "Legacy .doc format has limited support. Consider converting to .docx"
            )
        elif extension == ".odt":
            result.warning = "ODT support is experimental"
        elif extension == ".rtf":
            result.warning = "RTF support is experimental"

    return result


def convert_to_pil_image(file_path: Union[str, Path], page: int = 0) -> Optional[Any]:
    """Convert various image formats to PIL Image for processing.

    Args:
        file_path: Path to the image file
        page: Page number for multi-page images (0-indexed)

    Returns:
        PIL Image object or None if conversion fails
    """
    import PIL.Image

    file_path = Path(file_path)
    extension = file_path.suffix.lower()

    try:
        if extension == ".svg":
            return _convert_svg_to_pil(file_path)
        elif extension in (".heic", ".heif"):
            return _convert_heic_to_pil(file_path)
        elif extension == ".avif":
            return _convert_avif_to_pil(file_path)
        elif extension == ".psd":
            return _convert_psd_to_pil(file_path, page)
        elif extension in NEEDS_MULTI_PAGE_HANDLING:
            return _load_multi_page_image(file_path, page)
        elif extension == ".eps":
            return _convert_eps_to_pil(file_path)
        else:
            return PIL.Image.open(file_path)
    except Exception as e:
        logger.error(f"Failed to convert {extension} to PIL Image: {e}")
        return None


def _convert_svg_to_pil(file_path: Path) -> Optional[Any]:
    """Convert SVG to PIL Image using cairosvg or inkscape."""
    import PIL.Image

    try:
        import cairosvg

        png_data = cairosvg.svg2png(
            url=str(file_path), output_width=2048, output_height=2048
        )
        return PIL.Image.open(io.BytesIO(png_data))
    except ImportError:
        logger.warning("cairosvg not installed. SVG conversion unavailable.")
        logger.info("Install with: pip install cairosvg")

    try:
        import subprocess

        result = subprocess.run(
            [
                "inkscape",
                str(file_path),
                "--export-filename=png",
                "--export-width=2048",
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            png_path = file_path.with_suffix(".png")
            if png_path.exists():
                return PIL.Image.open(png_path)
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    logger.error("No SVG converter available. Install cairosvg: pip install cairosvg")
    return None


def _convert_heic_to_pil(file_path: Path) -> Optional[Any]:
    """Convert HEIC/HEIF to PIL Image."""
    import PIL.Image

    try:
        from pillow_heif import HeifIO

        heif_file = HeifIO.from_file(str(file_path))
        return heif_file.to_pillow()
    except ImportError:
        pass

    try:
        import pillow_heif

        heif = pillow_heif.open(file_path)
        return heif.to_pillow()
    except ImportError:
        pass

    try:
        import subprocess

        result = subprocess.run(
            ["magick", "convert", str(file_path), "png:-"],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return PIL.Image.open(io.BytesIO(result.stdout))
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    logger.error(
        "HEIC conversion unavailable. Install pillow-heif: pip install pillow-heif"
    )
    return None


def _convert_avif_to_pil(file_path: Path) -> Optional[Any]:
    """Convert AVIF to PIL Image."""
    import PIL.Image

    try:
        from pillow_avif import AvifImagePlugin

        return PIL.Image.open(file_path)
    except ImportError:
        pass

    try:
        import subprocess

        result = subprocess.run(
            ["magick", "convert", str(file_path), "png:-"],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return PIL.Image.open(io.BytesIO(result.stdout))
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    logger.error(
        "AVIF conversion unavailable. Install pillow-avif: pip install pillow-avif"
    )
    return None


def _convert_psd_to_pil(file_path: Path, page: int = 0) -> Optional[Any]:
    """Convert PSD to PIL Image."""
    import PIL.Image
    import PIL.PsdImagePlugin

    try:
        with PIL.Image.open(file_path) as img:
            if hasattr(img, "n_frames") and img.n_frames > 1:
                img.seek(page)
            return img.copy()
    except Exception as e:
        logger.error(f"Failed to convert PSD: {e}")
        return None


def _load_multi_page_image(file_path: Path, page: int = 0) -> Optional[Any]:
    """Load a specific page from multi-page image formats."""
    import PIL.Image

    try:
        with PIL.Image.open(file_path) as img:
            try:
                for _ in range(page + 1):
                    try:
                        img.seek(img.tell() + 1 if img.tell() > 0 else 0)
                    except EOFError:
                        break
                img.seek(0)
                for _ in range(page):
                    img.seek(img.tell() + 1)
            except (AttributeError, EOFError):
                pass
            return img.copy()
    except Exception as e:
        logger.error(f"Failed to load multi-page image: {e}")
        return None


def _convert_eps_to_pil(file_path: Path) -> Optional[Any]:
    """Convert EPS to PIL Image."""
    import PIL.Image

    try:
        import subprocess

        result = subprocess.run(
            [
                "gs",
                "-dNOPAUSE",
                "-dBATCH",
                "-sDEVICE=png16m",
                f"-sOutputFile=/dev/stdout",
                str(file_path),
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout:
            return PIL.Image.open(io.BytesIO(result.stdout))
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    try:
        with PIL.Image.open(file_path) as img:
            return img.copy()
    except Exception:
        pass

    logger.error(
        "EPS conversion unavailable. Install Ghostscript for better EPS support"
    )
    return None


def prepare_image_for_analysis(
    file_path: Union[str, Path],
) -> Optional[Tuple[Any, bool]]:
    """Prepare any image for OpenCV analysis by converting to 8-bit grayscale.

    Args:
        file_path: Path to the image file

    Returns:
        Tuple of (image, was_converted) or None if preparation fails
    """
    import cv2
    import PIL.Image

    pil_img = convert_to_pil_image(file_path)
    if pil_img is None:
        return None

    was_converted = False

    if pil_img.mode == "RGBA":
        background = PIL.Image.new("RGB", pil_img.size, (255, 255, 255))
        background.paste(pil_img, mask=pil_img.split()[3])
        pil_img = background
        was_converted = True

    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
        was_converted = True

    img_array = np.array(pil_img)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

    if gray.dtype != np.uint8:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        was_converted = True

    return gray, was_converted


def get_all_pages(file_path: Union[str, Path]) -> List[Any]:
    """Get all pages/frames from a multi-page image file.

    Args:
        file_path: Path to the image file

    Returns:
        List of PIL Image objects
    """
    import PIL.Image

    file_path = Path(file_path)
    images = []

    try:
        with PIL.Image.open(file_path) as img:
            page = 0
            while True:
                try:
                    img.seek(page)
                    images.append(img.copy())
                    page += 1
                except EOFError:
                    break
    except Exception as e:
        logger.error(f"Failed to read pages from {file_path}: {e}")

    return images if images else [PIL.Image.open(file_path)]


def convert_document_to_text(file_path: Union[str, Path]) -> Optional[str]:
    """Extract text content from various document formats.

    Args:
        file_path: Path to the document file

    Returns:
        Extracted text content or None if extraction fails
    """
    file_path = Path(file_path)
    extension = file_path.suffix.lower()
    detected_format, _ = detect_format_by_magic(file_path)
    effective_format = detected_format if detected_format in {"docx", "pptx", "odt", "rtf"} else extension.lstrip(".")

    if effective_format == "odt":
        return _extract_odt_text(file_path)
    elif effective_format == "rtf":
        return _extract_rtf_text(file_path)
    elif effective_format == "pptx":
        return _extract_pptx_text(file_path)
    elif effective_format in {"doc", "ppt"}:
        return _extract_legacy_office_text(file_path)

    return None


def _extract_odt_text(file_path: Path) -> Optional[str]:
    """Extract text from ODT (OpenDocument Text) files."""
    import zipfile
    import xml.etree.ElementTree as ET

    try:
        with zipfile.ZipFile(file_path, "r") as z:
            with z.open("content.xml") as f:
                tree = ET.parse(f)
                root = tree.getroot()

                namespaces = {
                    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
                    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
                }

                text_content = []
                for elem in root.iter():
                    if elem.text and elem.text.strip():
                        text_content.append(elem.text.strip())
                    if elem.tail and elem.tail.strip():
                        text_content.append(elem.tail.strip())

                return "\n".join(text_content)
    except Exception as e:
        logger.error(f"Failed to extract ODT text: {e}")
        return None


def _extract_rtf_text(file_path: Path) -> Optional[str]:
    """Extract plain text from RTF files."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        import re

        text = re.sub(r"\\[a-z]+\d*\s?", " ", content)
        text = re.sub(r"\{\\}", "", text)
        text = re.sub(r"[{}\\]", "", text)
        text = re.sub(r"\s+", " ", text)

        return text.strip()
    except Exception as e:
        logger.error(f"Failed to extract RTF text: {e}")
        return None


def _extract_pptx_text(file_path: Path) -> Optional[str]:
    """Extract plain text from PPTX presentation slides."""
    import zipfile
    import xml.etree.ElementTree as ET

    text_content: List[str] = []

    try:
        with zipfile.ZipFile(file_path, "r") as archive:
            slide_names = sorted(
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )

            for slide_name in slide_names:
                try:
                    root = ET.fromstring(archive.read(slide_name))
                except ET.ParseError:
                    continue

                for elem in root.iter():
                    if elem.text and elem.text.strip():
                        text_content.append(elem.text.strip())
        return "\n".join(text_content) if text_content else None
    except Exception as e:
        logger.error(f"Failed to extract PPTX text: {e}")
        return None


def _extract_legacy_office_text(file_path: Path) -> Optional[str]:
    """Extract text from legacy DOC/PPT files using local converters when available."""
    import re
    import subprocess

    commands = [
        ["textutil", "-convert", "txt", "-stdout", str(file_path)],
        ["strings", str(file_path)],
    ]

    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            continue

        output = (result.stdout or "").strip()
        if output:
            return output

    try:
        content = file_path.read_bytes().decode("latin-1", errors="ignore")
    except Exception as e:
        logger.error(f"Failed to read legacy Office file {file_path}: {e}")
        return None

    text_chunks = re.findall(r"[A-Za-z0-9][A-Za-z0-9 ,.;:'\"()/_-]{4,}", content)
    normalized_chunks = [chunk.strip() for chunk in text_chunks if chunk.strip()]
    return "\n".join(normalized_chunks[:200]) if normalized_chunks else None


def get_supported_formats_summary() -> Dict[str, List[str]]:
    """Get summary of all supported formats."""
    return {
        "images": sorted(list(SUPPORTED_IMAGE_EXTENSIONS)),
        "documents": sorted(list(SUPPORTED_DOCUMENT_EXTENSIONS)),
        "fonts": sorted(list(SUPPORTED_FONT_EXTENSIONS)),
        "needs_conversion": sorted(list(CONVERTIBLE_TO_PNG)),
        "multi_page": sorted(list(NEEDS_MULTI_PAGE_HANDLING)),
    }
