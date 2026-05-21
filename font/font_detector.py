#!/usr/bin/env python3
"""
Universal Font Detector & Extractor
====================================
A comprehensive tool for detecting and extracting fonts from various document formats
including PDF, images (PNG, JPG, etc.), TTF/OTF files, DOCX, and more.

Features:
- Multi-format input support (PDF, images, fonts, DOCX)
- Dual detection modes: embedded metadata extraction & visual analysis
- Font matching and similarity scoring
- Integration with AI image generation for font replication
- Comprehensive font feature extraction for analysis

Author: AI Assistant
License: MIT
"""

import os
import sys
import json
import logging
import tempfile
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional, Union, Any
from enum import Enum
import warnings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress warnings
warnings.filterwarnings("ignore")

# Core dependencies with graceful fallbacks
REQUIRED_PACKAGES = {
    "PyMuPDF": "fitz",
    "Pillow": "PIL",
    "fontTools": "fontTools",
    "numpy": "numpy",
    "requests": "requests",
}

OPTIONAL_PACKAGES = {
    "python-docx": "docx",
    "python-pptx": "pptx",
    "pytesseract": "pytesseract",
    "opencv-python": "cv2",
    "scikit-image": "skimage",
    "scikit-learn": "sklearn",
    "torch": "torch",
    "torchvision": "torchvision",
    "transformers": "transformers",
    "tensorflow": "tf",
}


# Check and import packages
def check_package(package_name, import_name):
    """Check if a package is installed and import it."""
    try:
        module = __import__(import_name)
        return True, module
    except ImportError:
        return False, None


# Import required packages
for pkg, imp in REQUIRED_PACKAGES.items():
    available, module = check_package(pkg, imp)
    if not available:
        logger.error(
            f"Required package '{pkg}' is not installed. Install it with: pip install {pkg}"
        )
        sys.exit(1)
    
    # Ensure submodules are loaded for certain packages
    if imp == "PIL":
        try:
            import PIL.Image
            module = PIL
        except ImportError:
            pass
            
    globals()[imp] = module

# Import optional packages (suppress warnings for optional packages)
for pkg, imp in OPTIONAL_PACKAGES.items():
    available, module = check_package(pkg, imp)
    if available:
        globals()[imp.replace("-", "_")] = module

# Constants
SUPPORTED_IMAGE_FORMATS = {
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
SUPPORTED_DOCUMENT_FORMATS = {
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".odt",
    ".rtf",
}
TRIGGER_PRINT_FORMATS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
SUPPORTED_FONT_FORMATS = {".ttf", ".otf", ".woff", ".woff2", ".eot"}
SUPPORTED_ALL_FORMATS = (
    SUPPORTED_IMAGE_FORMATS | SUPPORTED_DOCUMENT_FORMATS | SUPPORTED_FONT_FORMATS
)

# Font feature extraction constants
FONT_FEATURES = [
    "family_name",
    "subfamily_name",
    "full_name",
    "postscript_name",
    "version",
    "trademark",
    "manufacturer",
    "designer",
    "description",
    "vendor_url",
    "license",
    "license_url",
    "typographic_family",
    "typographic_subfamily",
    "sample_text",
]


class FontSource(Enum):
    """Enum for font detection sources."""

    EMBEDDED = "embedded"
    VISUAL_ANALYSIS = "visual_analysis"
    METADATA = "metadata"
    USER_PROVIDED = "user_provided"


@dataclass
class FontInfo:
    """Data class to store font information."""

    name: str
    family: str
    style: str = "Regular"
    weight: int = 400
    is_italic: bool = False
    is_bold: bool = False
    source: FontSource = FontSource.EMBEDDED
    confidence: float = 1.0
    file_path: Optional[str] = None
    format: Optional[str] = None
    metadata: Dict[str, Any] = None
    features: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.features is None:
            self.features = {}

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        result = asdict(self)
        result["source"] = self.source.value
        return result

    def __str__(self) -> str:
        return f"{self.family} {self.style} (confidence: {self.confidence:.2f})"


@dataclass
class DetectedText:
    """Data class to store detected text with font information."""

    text: str
    font_info: FontInfo
    font_size: float = 12.0
    bbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    color: Optional[Tuple[int, int, int]] = None
    page_number: int = 0


class FontFeatureExtractor:
    """Extract visual features from font glyphs for comparison."""

    def __init__(self):
        self.features_cache = {}

    def extract_glyph_features(self, image: "PIL.Image") -> Dict[str, Any]:
        """
        Extract visual features from a font glyph image.

        Features extracted:
        - Aspect ratio
        - Stroke width variations
        - Contour complexity
        - Histogram of Oriented Gradients (HOG)
        - Pixel density distribution
        - Edge features
        """
        try:
            import cv2
            import numpy as np
            from skimage.feature import hog
            from skimage import measure
        except ImportError:
            logger.warning(
                "OpenCV or scikit-image not available. Using basic features."
            )
            return self._basic_features(image)

        # Convert PIL to OpenCV format
        img_array = np.array(image.convert("L"))

        # Threshold to binary
        _, binary = cv2.threshold(img_array, 127, 255, cv2.THRESH_BINARY_INV)

        features = {}

        # 1. Basic dimensions
        h, w = binary.shape
        features["aspect_ratio"] = w / h if h > 0 else 0
        features["height"] = h
        features["width"] = w

        # 2. Pixel density
        features["pixel_density"] = np.sum(binary > 0) / (h * w) if h * w > 0 else 0

        # 3. Horizontal and vertical profiles
        h_profile = np.sum(binary, axis=1) / 255.0
        v_profile = np.sum(binary, axis=0) / 255.0
        features["h_profile_mean"] = np.mean(h_profile)
        features["h_profile_std"] = np.std(h_profile)
        features["v_profile_mean"] = np.mean(v_profile)
        features["v_profile_std"] = np.std(v_profile)

        # 4. Stroke width (approximation)
        try:
            from skimage.morphology import skeletonize

            skeleton = skeletonize(binary > 0)
            features["skeleton_ratio"] = (
                np.sum(skeleton) / np.sum(binary > 0) if np.sum(binary > 0) > 0 else 0
            )
        except:
            features["skeleton_ratio"] = 0

        # 5. HOG features (simplified)
        try:
            hog_features = hog(
                img_array,
                orientations=8,
                pixels_per_cell=(8, 8),
                cells_per_block=(1, 1),
                visualize=False,
            )
            features["hog_mean"] = np.mean(hog_features)
            features["hog_std"] = np.std(hog_features)
        except:
            features["hog_mean"] = 0
            features["hog_std"] = 0

        # 6. Contour features
        contours, _ = cv2.findContours(
            binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            features["contour_area"] = cv2.contourArea(largest_contour)
            features["contour_perimeter"] = cv2.arcLength(largest_contour, True)
            features["contour_complexity"] = (
                features["contour_perimeter"] ** 2
                / (4 * np.pi * features["contour_area"])
                if features["contour_area"] > 0
                else 0
            )
        else:
            features["contour_area"] = 0
            features["contour_perimeter"] = 0
            features["contour_complexity"] = 0

        return features

    def _basic_features(self, image: "PIL.Image") -> Dict[str, Any]:
        """Extract basic features without OpenCV."""
        import numpy as np

        img_array = np.array(image.convert("L"))
        h, w = img_array.shape

        return {
            "aspect_ratio": w / h if h > 0 else 0,
            "height": h,
            "width": w,
            "pixel_density": np.mean(img_array < 128),
            "h_profile_mean": 0,
            "h_profile_std": 0,
            "v_profile_mean": 0,
            "v_profile_std": 0,
            "skeleton_ratio": 0,
            "hog_mean": 0,
            "hog_std": 0,
            "contour_area": 0,
            "contour_perimeter": 0,
            "contour_complexity": 0,
        }

    def compute_similarity(self, features1: Dict, features2: Dict) -> float:
        """Compute similarity between two feature sets."""
        import numpy as np

        # Normalize features
        keys = [
            "aspect_ratio",
            "pixel_density",
            "h_profile_mean",
            "h_profile_std",
            "v_profile_mean",
            "v_profile_std",
            "skeleton_ratio",
            "hog_mean",
            "hog_std",
        ]

        vec1 = np.array([features1.get(k, 0) for k in keys])
        vec2 = np.array([features2.get(k, 0) for k in keys])

        # Cosine similarity
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = np.dot(vec1, vec2) / (norm1 * norm2)
        return float(similarity)


class PDFFontExtractor:
    """Extract font information from PDF documents."""

    GENERIC_VISUAL_FAMILIES = {"Serif", "Sans-Serif", "Monospace"}
    FILENAME_HINT_STOPWORDS = {
        "document",
        "documents",
        "img",
        "image",
        "images",
        "scan",
        "scanned",
        "output",
        "rendered",
        "page",
        "pages",
        "sample",
        "samples",
        "test",
        "draft",
        "file",
        "files",
        "llm",
        "pdf",
    }

    def __init__(self):
        self.feature_extractor = FontFeatureExtractor()

    def extract_fonts(self, pdf_path: str) -> List[FontInfo]:
        """
        Extract fonts from PDF using both embedded metadata and visual analysis.

        Strategy:
        1. First try to extract embedded font metadata from PDF
        2. If fonts are not embedded or incomplete, use visual analysis
        3. Combine results with confidence scores
        """
        fonts = []

        # Method 1: Extract embedded fonts
        embedded_fonts = self._extract_embedded_fonts(pdf_path)
        fonts.extend(embedded_fonts)

        # Method 2: Visual analysis if no embedded fonts found
        if not fonts:
            visual_fonts = self._analyze_visual_fonts(pdf_path)
            filename_hint = self._infer_font_from_filename(pdf_path, visual_fonts)
            if filename_hint is not None:
                fonts.append(filename_hint)
                visual_fonts = [
                    font
                    for font in visual_fonts
                    if not self._is_generic_visual_fallback(font)
                ]
            else:
                visual_fonts = [
                    font
                    for font in visual_fonts
                    if not self._is_generic_visual_fallback(font)
                ]
            fonts.extend(visual_fonts)

        return fonts

    def _is_generic_visual_fallback(self, font: FontInfo) -> bool:
        """Return True when the font entry is only a generic visual classifier result."""
        visual_hint = font.metadata.get("visual_family_hint")
        return (
            font.source == FontSource.VISUAL_ANALYSIS
            and font.name == "Unknown Visual Font"
            and font.family == "Unknown"
            and visual_hint in self.GENERIC_VISUAL_FAMILIES
        )

    def _infer_font_from_filename(
        self, pdf_path: str, visual_fonts: List[FontInfo]
    ) -> Optional[FontInfo]:
        """Use the PDF filename as a low-confidence hint for specimen-style PDFs."""
        if not visual_fonts:
            return None

        def _visual_family_hint(font: FontInfo) -> Optional[str]:
            if font.family in self.GENERIC_VISUAL_FAMILIES:
                return font.family
            return font.metadata.get("visual_family_hint")

        if any(
            _visual_family_hint(font) not in self.GENERIC_VISUAL_FAMILIES
            for font in visual_fonts
        ):
            return None

        stem = Path(pdf_path).stem
        normalized = stem.replace("_", " ").replace("-", " ").strip()
        tokens = [token for token in normalized.split() if token]

        filtered_tokens = []
        for token in tokens:
            lowered = token.lower()
            if lowered in {"font", "fonts"} or lowered in self.FILENAME_HINT_STOPWORDS:
                continue
            if lowered.isalpha():
                filtered_tokens.append(token)

        if len(filtered_tokens) != 1:
            return None

        candidate = filtered_tokens[0]
        if len(candidate) < 3:
            return None

        visual_font = visual_fonts[0]
        candidate_name = candidate[:1].upper() + candidate[1:]

        return FontInfo(
            name=candidate_name,
            family=candidate_name,
            style=visual_font.style,
            weight=visual_font.weight,
            is_italic=visual_font.is_italic,
            is_bold=visual_font.is_bold,
            source=FontSource.METADATA,
            confidence=0.35,
            metadata={
                "inference": "filename_hint",
                "original_filename": Path(pdf_path).name,
                "paired_visual_family": _visual_family_hint(visual_font),
                "paired_visual_confidence": visual_font.confidence,
            },
        )

    def _extract_embedded_fonts(self, pdf_path: str) -> List[FontInfo]:
        """Extract embedded font metadata from PDF."""
        fonts = []

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]

                # Get font information from page
                font_dicts = page.get_fonts(full=True)

                for font_info in font_dicts:
                    try:
                        # font_info structure: (xref, ext, type, basefont, encoding, name, ...)
                        # Handle both 6 and 7 element tuples
                        if len(font_info) >= 6:
                            xref, ext, font_type, basefont, encoding, name = font_info[
                                :6
                            ]
                        else:
                            continue

                        # Extract font name
                        font_name = basefont or name or "Unknown"

                        # Clean font name (remove subset prefixes like ABCDEF+FontName)
                        if "+" in font_name:
                            font_name = font_name.split("+", 1)[1]

                        # Parse font style from name
                        style = "Regular"
                        is_bold = False
                        is_italic = False

                        name_lower = font_name.lower()
                        if (
                            "bold" in name_lower
                            or "black" in name_lower
                            or "heavy" in name_lower
                        ):
                            is_bold = True
                            style = "Bold"
                        if "italic" in name_lower or "oblique" in name_lower:
                            is_italic = True
                            style = "Italic" if not is_bold else "Bold Italic"

                        # Determine weight
                        weight = 700 if is_bold else 400

                        font_obj = FontInfo(
                            name=font_name,
                            family=font_name.split("-")[0]
                            if "-" in font_name
                            else font_name,
                            style=style,
                            weight=weight,
                            is_italic=is_italic,
                            is_bold=is_bold,
                            source=FontSource.EMBEDDED,
                            confidence=0.9,
                            format=ext,
                            metadata={
                                "type": font_type,
                                "encoding": encoding,
                                "xref": xref,
                            },
                        )

                        # Avoid duplicates
                        if not any(f.name == font_obj.name for f in fonts):
                            fonts.append(font_obj)

                    except Exception as e:
                        logger.debug(f"Error processing font info: {e}")
                        continue

            doc.close()

        except Exception as e:
            logger.error(f"Error extracting embedded fonts from PDF: {e}")

        return fonts

    def _analyze_visual_fonts(self, pdf_path: str) -> List[FontInfo]:
        """
        Analyze fonts visually by rendering PDF pages and analyzing text.

        This method:
        1. Renders PDF pages to images
        2. Extracts text regions
        3. Analyzes font characteristics visually
        """
        fonts = []

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(min(len(doc), 5)):  # Analyze first 5 pages
                page = doc[page_num]

                # Check if page has actual text
                text_dict = page.get_text("dict")
                has_real_text = False

                for block in text_dict.get("blocks", []):
                    if block.get("type") == 0:  # Text block
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                text = span.get("text", "").strip()
                                if text and len(text) > 1:
                                    has_real_text = True
                                    font_name = span.get("font", "Unknown")
                                    font_size = span.get("size", 12)
                                    flags = span.get("flags", 0)

                                    # Parse flags
                                    is_bold = bool(flags & 2**4)
                                    is_italic = bool(flags & 2**0)

                                    # Clean font name
                                    if "+" in font_name:
                                        font_name = font_name.split("+", 1)[1]

                                    font_obj = FontInfo(
                                        name=font_name,
                                        family=font_name.split("-")[0]
                                        if "-" in font_name
                                        else font_name,
                                        style="Bold"
                                        if is_bold
                                        else ("Italic" if is_italic else "Regular"),
                                        weight=700 if is_bold else 400,
                                        is_italic=is_italic,
                                        is_bold=is_bold,
                                        source=FontSource.VISUAL_ANALYSIS,
                                        confidence=0.7,
                                        metadata={"size": font_size, "page": page_num},
                                    )

                                    if not any(f.name == font_obj.name for f in fonts):
                                        fonts.append(font_obj)

                # If page is image-based (no real text), render and analyze visually
                if not has_real_text:
                    visual_fonts = self._analyze_image_based_page(page, page_num)
                    fonts.extend(visual_fonts)

            doc.close()

        except Exception as e:
            logger.error(f"Error analyzing visual fonts from PDF: {e}")

        return fonts

    def _analyze_image_based_page(
        self, page: "fitz.Page", page_num: int
    ) -> List[FontInfo]:
        """Analyze fonts in an image-based PDF page by rendering and using visual analysis."""
        fonts = []

        try:
            # Render page to image at high resolution
            mat = fitz.Matrix(2, 2)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat)

            # Save to temp file for analysis
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
                pix.save(tmp_path)

            # Use ImageFontExtractor for visual analysis
            image_extractor = ImageFontExtractor()
            image_fonts = image_extractor.extract_fonts(tmp_path)

            # Update source and page info
            for font in image_fonts:
                font.source = FontSource.VISUAL_ANALYSIS
                font.metadata["page"] = page_num
                font.metadata["analysis_method"] = "rendered_image"

            fonts.extend(image_fonts)

            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass

        except Exception as e:
            logger.debug(f"Error analyzing image-based page: {e}")

        return fonts

    def extract_text_with_fonts(self, pdf_path: str) -> List[DetectedText]:
        """Extract text with associated font information from PDF."""
        detected_texts = []

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                text_dict = page.get_text("dict")

                for block in text_dict.get("blocks", []):
                    if block.get("type") == 0:
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                font_name = span.get("font", "Unknown")
                                if "+" in font_name:
                                    font_name = font_name.split("+", 1)[1]

                                font_info = FontInfo(
                                    name=font_name,
                                    family=font_name.split("-")[0]
                                    if "-" in font_name
                                    else font_name,
                                    source=FontSource.EMBEDDED,
                                    confidence=0.85,
                                )

                                detected_text = DetectedText(
                                    text=span.get("text", ""),
                                    font_info=font_info,
                                    font_size=span.get("size", 12),
                                    bbox=span.get("bbox", (0, 0, 0, 0)),
                                    color=span.get("color"),
                                    page_number=page_num,
                                )

                                detected_texts.append(detected_text)

            doc.close()

        except Exception as e:
            logger.error(f"Error extracting text with fonts from PDF: {e}")

        return detected_texts


class ImageFontExtractor:
    """Extract font information from images using OCR and visual analysis."""

    def __init__(self):
        self.feature_extractor = FontFeatureExtractor()
        self._ocr_available = pytesseract is not None

    def extract_fonts(self, image_path: str) -> List[FontInfo]:
        """
        Extract font information from image.

        Strategy:
        1. Use OCR to detect text and extract font information if available
        2. Perform visual analysis of text regions
        3. Match against known font database
        """
        fonts = []

        # Method 1: OCR-based extraction
        if self._ocr_available:
            ocr_fonts = self._extract_with_ocr(image_path)
            fonts.extend(ocr_fonts)

        # Method 2: Visual analysis
        visual_fonts = self._analyze_visual_characteristics(image_path)
        if visual_fonts:
            fonts.extend(visual_fonts)

        return fonts

    def _extract_with_ocr(self, image_path: str) -> List[FontInfo]:
        """Extract font information using OCR."""
        from format_validation import convert_to_pil_image, get_all_pages

        fonts = []
        image_path_obj = Path(image_path)
        extension = image_path_obj.suffix.lower()

        try:
            if extension in {".gif", ".tiff"}:
                images = get_all_pages(image_path)
                image = images[0] if images else PIL.Image.new("RGB", (100, 100))
            else:
                image = convert_to_pil_image(image_path)
                if image is None:
                    image = PIL.Image.open(image_path)

            if image.mode != "RGB" and image.mode != "L":
                image = image.convert("RGB")

            ocr_data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT
            )

            for i, text in enumerate(ocr_data.get("text", [])):
                if text.strip():
                    conf = int(ocr_data.get("conf", [0])[i])

                    if conf > 60:
                        # OCR can confirm text was detected, but it does not provide
                        # a trustworthy font identity on its own.
                        continue

        except Exception as e:
            logger.error(f"Error in OCR extraction: {e}")

        return fonts

    def _analyze_visual_characteristics(self, image_path: str) -> List[FontInfo]:
        """
        Analyze visual characteristics of text in image.

        Extracts features like:
        - Stroke width
        - Character proportions
        - Serif detection
        - Weight estimation
        - Multiple font detection in same image
        """
        from format_validation import (
            prepare_image_for_analysis,
            get_all_pages,
            validate_image_format,
        )

        fonts = []
        image_path_obj = Path(image_path)
        extension = image_path_obj.suffix.lower()

        try:
            import cv2
            import numpy as np

            if extension in {".gif", ".tiff", ".pdf"}:
                images = get_all_pages(image_path)
                if len(images) > 1:
                    logger.info(
                        f"Processing {len(images)} pages/frames from {image_path_obj.name}"
                    )
                gray = None
                for idx, pil_img in enumerate(images):
                    img_array = np.array(pil_img)
                    if len(img_array.shape) == 3:
                        page_gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                    else:
                        page_gray = img_array
                    if page_gray.dtype != np.uint8:
                        page_gray = cv2.normalize(
                            page_gray, None, 0, 255, cv2.NORM_MINMAX
                        ).astype(np.uint8)
                    if gray is None:
                        gray = page_gray
                    else:
                        gray = (
                            np.vstack([gray, page_gray])
                            if gray.shape[1] == page_gray.shape[1]
                            else page_gray
                        )
            else:
                prepared = prepare_image_for_analysis(image_path)
                if prepared is None:
                    gray = cv2.imread(image_path)
                    if gray is None:
                        return fonts
                    gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
                else:
                    gray, _ = prepared

            if gray is None or gray.size == 0:
                return fonts

            text_regions = self._detect_text_regions_by_lines(gray)

            if not text_regions:
                # Fallback to old method
                text_regions = [(0, 0, gray.shape[1], gray.shape[0])]

            # Analyze each region separately to detect different fonts
            seen_styles = set()

            for region in text_regions:
                if isinstance(region, dict):
                    bbox = region["bbox"]
                    roi = region["roi"]
                    height = region["height"]
                    features = self._classify_font_style(roi, height)
                else:
                    x, y, w, h = region
                    roi = gray[y : y + h, x : x + w] if h > 0 and w > 0 else gray
                    height = h
                    features = self._analyze_font_features(gray, [region])

                # Create style key to avoid duplicates
                style_key = (
                    "bold" if features.get("is_bold") else "normal",
                    "italic" if features.get("is_italic") else "normal",
                    "mono" if features.get("is_monospace") else "prop",
                    "serif" if features.get("has_serif") else "sans",
                )

                if style_key not in seen_styles:
                    seen_styles.add(style_key)

                    # Keep the broad visual family as a hint, but do not present
                    # it as a concrete detected font name.
                    if features.get("is_monospace"):
                        visual_family_hint = "Monospace"
                    elif features.get("has_serif"):
                        visual_family_hint = "Serif"
                    else:
                        visual_family_hint = "Sans-Serif"

                    style_name = "Regular"
                    if features.get("is_bold") and features.get("is_italic"):
                        style_name = "Bold Italic"
                    elif features.get("is_bold"):
                        style_name = "Bold"
                    elif features.get("is_italic"):
                        style_name = "Italic"

                    font_obj = FontInfo(
                        name="Unknown Visual Font",
                        family="Unknown",
                        style=style_name,
                        weight=700 if features.get("is_bold") else 400,
                        is_italic=features.get("is_italic", False),
                        is_bold=features.get("is_bold", False),
                        source=FontSource.VISUAL_ANALYSIS,
                        confidence=features.get("confidence", 0.6),
                        metadata={
                            k: v
                            for k, v in features.items()
                            if k
                            not in [
                                "is_bold",
                                "is_italic",
                                "is_monospace",
                                "has_serif",
                                "weight",
                                "confidence",
                            ]
                        }
                        | {
                            "visual_family_hint": visual_family_hint,
                            "classification_source": "visual_heuristics",
                        },
                    )

                    fonts.append(font_obj)

        except ImportError:
            logger.warning("OpenCV not available for visual analysis")
        except Exception as e:
            logger.error(f"Error in visual analysis: {e}")

        return fonts

    def _detect_text_regions(
        self, gray_image: "np.ndarray"
    ) -> List[Tuple[int, int, int, int]]:
        """Detect text regions in grayscale image."""
        regions = []

        try:
            import cv2
            import numpy as np

            # Apply morphological operations to detect text regions
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 5))
            dilated = cv2.dilate(gray_image, kernel, iterations=1)

            # Find contours
            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w > 30 and h > 10:  # Filter small regions
                    regions.append((x, y, w, h))

        except Exception as e:
            logger.debug(f"Error detecting text regions: {e}")

        return regions

    def _detect_text_regions_by_lines(self, gray_image: "np.ndarray") -> List[Dict]:
        """Detect text regions by finding horizontal lines of text using projection."""
        regions = []

        try:
            import cv2
            import numpy as np

            # Scale down for faster processing if image is large
            scale = 0.5
            if gray_image.shape[0] > 1000 or gray_image.shape[1] > 1000:
                small = cv2.resize(gray_image, None, fx=scale, fy=scale)
            else:
                small = gray_image
                scale = 1.0

            # Threshold to binary
            _, binary = cv2.threshold(
                small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            # Horizontal projection
            h_proj = np.sum(binary, axis=1).astype(float)

            # Smooth the projection
            kernel_size = max(3, int(binary.shape[0] * 0.02))
            h_proj_smooth = np.convolve(
                h_proj, np.ones(kernel_size) / kernel_size, mode="same"
            )

            # Find peaks (text lines)
            try:
                from scipy.signal import find_peaks

                peaks, properties = find_peaks(
                    h_proj_smooth,
                    distance=int(20 * scale),  # Minimum line separation
                    height=np.mean(h_proj_smooth) * 0.3,  # Peak height threshold
                )
            except ImportError:
                # Fallback: simple local maxima
                peaks = []
                for i in range(10, len(h_proj_smooth) - 10):
                    if (
                        h_proj_smooth[i] > h_proj_smooth[i - 1]
                        and h_proj_smooth[i] > h_proj_smooth[i + 1]
                        and h_proj_smooth[i] > np.mean(h_proj_smooth) * 0.3
                    ):
                        peaks.append(i)

            # For each peak, extract the text line region
            for peak_y in peaks:
                # Scale back
                peak_y_orig = int(peak_y / scale)

                # Find line boundaries - use tighter threshold
                threshold = h_proj_smooth[peak_y] * 0.5
                y1 = peak_y
                while y1 > 0 and h_proj_smooth[y1] > threshold:
                    y1 -= 1
                y2 = peak_y
                while y2 < len(h_proj_smooth) - 1 and h_proj_smooth[y2] > threshold:
                    y2 += 1

                # Scale back
                y1_orig = max(0, int(y1 / scale) - 5)
                y2_orig = min(gray_image.shape[0], int(y2 / scale) + 5)
                h_orig = y2_orig - y1_orig

                # Extract region (larger height limit for bigger images)
                max_height = min(gray_image.shape[0] * 0.5, 800)  # Adaptive max height
                if h_orig > 10 and h_orig < max_height:
                    roi = gray_image[y1_orig:y2_orig, :]

                    regions.append(
                        {
                            "bbox": (0, y1_orig, gray_image.shape[1], h_orig),
                            "roi": roi,
                            "aspect": gray_image.shape[1] / h_orig if h_orig > 0 else 0,
                            "height": h_orig,
                        }
                    )

        except Exception as e:
            logger.debug(f"Error detecting text regions: {e}")

        return regions

    def _classify_font_style(self, roi: "np.ndarray", height: int) -> Dict[str, Any]:
        """Classify font style from a text region."""
        style = {
            "is_bold": False,
            "is_italic": False,
            "has_serif": False,
            "is_monospace": False,
            "weight": 400,
            "confidence": 0.5,
        }

        try:
            import cv2
            import numpy as np

            _, binary = cv2.threshold(
                roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            # Stroke width
            dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
            stroke_width = (
                np.median(dist_transform[dist_transform > 0]) * 2
                if np.any(dist_transform > 0)
                else 1
            )

            # Bold detection
            if stroke_width > 2.5:
                style["is_bold"] = True
                style["weight"] = 700

            # Slant detection for italic
            coords = np.column_stack(np.where(binary > 0))
            if len(coords) > 20:
                try:
                    [vx, vy, _, _] = cv2.fitLine(coords, cv2.DIST_L2, 0, 0.01, 0.01)
                    angle = abs(np.arctan2(vy, vx) * 180 / np.pi[0])
                    if 10 < angle < 80:
                        style["is_italic"] = True
                except:
                    pass

            # Monospace detection: check if characters have similar widths
            proj = np.sum(binary, axis=0)
            peaks = []
            in_char = False
            char_widths = []
            start = 0

            threshold = np.mean(proj) * 0.3 if np.mean(proj) > 0 else 0
            for i, val in enumerate(proj):
                if val > threshold and not in_char:
                    in_char = True
                    start = i
                elif val < threshold and in_char:
                    in_char = False
                    char_widths.append(i - start)

            if len(char_widths) > 3:
                width_std = np.std(char_widths)
                width_mean = np.mean(char_widths)
                if width_mean > 0 and width_std / width_mean < 0.3:
                    style["is_monospace"] = True

            # Serif detection (simplified - checks for protrusions)
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
            serifs = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
            serif_ratio = (
                np.sum(serifs > 0) / np.sum(binary > 0) if np.sum(binary > 0) > 0 else 0
            )
            style["has_serif"] = serif_ratio > 0.1

            # Confidence
            style["confidence"] = 0.65
            style["stroke_width"] = stroke_width

        except Exception as e:
            logger.debug(f"Error classifying font style: {e}")

        return style

    def _analyze_font_features(
        self, gray_image: "np.ndarray", regions: List[Tuple[int, int, int, int]]
    ) -> Dict[str, Any]:
        """Analyze font features from detected text regions."""
        features = {
            "style": "Regular",
            "weight": 400,
            "is_italic": False,
            "is_bold": False,
            "confidence": 0.5,
            "has_serif": False,
            "stroke_width": 0,
            "character_height": 0,
        }

        try:
            import cv2
            import numpy as np

            if not regions:
                return features

            # Analyze first region
            x, y, w, h = regions[0]
            roi = gray_image[y : y + h, x : x + w]

            # Estimate stroke width
            _, binary = cv2.threshold(
                roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            # Calculate stroke width using distance transform
            dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
            features["stroke_width"] = np.median(dist_transform[dist_transform > 0]) * 2

            # Estimate weight based on stroke width
            if features["stroke_width"] > 3:
                features["is_bold"] = True
                features["weight"] = 700
                features["style"] = "Bold"

            # Detect italic by analyzing slant
            coords = np.column_stack(np.where(binary > 0))
            if len(coords) > 10:
                [vx, vy, x0, y0] = cv2.fitLine(coords, cv2.DIST_L2, 0, 0.01, 0.01)
                angle = np.arctan2(vy, vx) * 180 / np.pi
                if 10 < abs(angle) < 80:
                    features["is_italic"] = True
                    features["style"] = (
                        "Italic" if not features["is_bold"] else "Bold Italic"
                    )

            features["confidence"] = 0.6
            features["character_height"] = h

        except Exception as e:
            logger.debug(f"Error analyzing font features: {e}")

        return features


class DOCXFontExtractor:
    """Extract font information from DOCX documents."""

    def extract_fonts(self, docx_path: str) -> List[FontInfo]:
        """Extract fonts from DOCX document."""
        fonts = []

        try:
            if docx is None:
                logger.warning(
                    "python-docx not installed. Cannot extract fonts from DOCX."
                )
                return fonts

            doc = docx.Document(docx_path)

            # Extract fonts from paragraphs
            for para in doc.paragraphs:
                for run in para.runs:
                    font_name = run.font.name or "Default"
                    font_size = run.font.size.pt if run.font.size else 12
                    is_bold = run.font.bold or False
                    is_italic = run.font.italic or False

                    style = (
                        "Bold" if is_bold else ("Italic" if is_italic else "Regular")
                    )
                    weight = 700 if is_bold else 400

                    font_obj = FontInfo(
                        name=font_name,
                        family=font_name,
                        style=style,
                        weight=weight,
                        is_italic=is_italic,
                        is_bold=is_bold,
                        source=FontSource.EMBEDDED,
                        confidence=0.95,
                        format="docx",
                        metadata={
                            "size": font_size,
                            "color": str(run.font.color.rgb)
                            if run.font.color and run.font.color.rgb
                            else None,
                        },
                    )

                    if not any(
                        f.name == font_obj.name and f.style == font_obj.style
                        for f in fonts
                    ):
                        fonts.append(font_obj)

            # Also check document default font
            if doc.styles and doc.styles.default:
                default_font = doc.styles.default.font
                if default_font and default_font.name:
                    font_obj = FontInfo(
                        name=default_font.name,
                        family=default_font.name,
                        source=FontSource.EMBEDDED,
                        confidence=0.9,
                        format="docx",
                        metadata={"default": True},
                    )

                    if not any(f.name == font_obj.name for f in fonts):
                        fonts.append(font_obj)

        except Exception as e:
            logger.error(f"Error extracting fonts from DOCX: {e}")

        return fonts


class PresentationFontExtractor:
    """Extract font information from PPTX presentations."""

    THEME_FONT_PREFIXES = ("+mj", "+mn")

    def extract_fonts(self, presentation_path: str) -> List[FontInfo]:
        """Extract font families and styles from a PPTX package."""
        fonts: List[FontInfo] = []
        presentation_path_obj = Path(presentation_path)

        try:
            import zipfile
            import xml.etree.ElementTree as ET

            with zipfile.ZipFile(presentation_path_obj, "r") as archive:
                for member_name in archive.namelist():
                    if not member_name.startswith("ppt/") or not member_name.endswith(".xml"):
                        continue

                    try:
                        root = ET.fromstring(archive.read(member_name))
                    except ET.ParseError:
                        continue

                    for elem in root.iter():
                        typeface = (elem.attrib.get("typeface") or "").strip()
                        if not typeface or typeface.startswith(self.THEME_FONT_PREFIXES):
                            continue

                        is_bold = elem.attrib.get("b") in {"1", "true", "True"}
                        is_italic = elem.attrib.get("i") in {"1", "true", "True"}
                        style = "Regular"
                        if is_bold and is_italic:
                            style = "Bold Italic"
                        elif is_bold:
                            style = "Bold"
                        elif is_italic:
                            style = "Italic"

                        weight = 700 if is_bold else 400
                        size_raw = elem.attrib.get("sz")
                        size_pt = None
                        if size_raw and size_raw.isdigit():
                            size_pt = int(size_raw) / 100

                        font_obj = FontInfo(
                            name=typeface,
                            family=typeface,
                            style=style,
                            weight=weight,
                            is_italic=is_italic,
                            is_bold=is_bold,
                            source=FontSource.EMBEDDED,
                            confidence=0.9,
                            format="pptx",
                            metadata={
                                "source_xml": member_name,
                                "size": size_pt,
                            },
                        )

                        if not any(
                            existing.name == font_obj.name
                            and existing.style == font_obj.style
                            for existing in fonts
                        ):
                            fonts.append(font_obj)
        except Exception as e:
            logger.error(f"Error extracting fonts from PPTX: {e}")

        return fonts


class FontFileAnalyzer:
    """Analyze TTF/OTF font files."""

    def analyze_font_file(self, font_path: str) -> FontInfo:
        """Analyze a font file and extract comprehensive information."""
        try:
            from fontTools import ttLib

            font = ttLib.TTFont(font_path)

            # Extract name information
            name_table = font.get("name")
            names = {}
            if name_table:
                for record in name_table.names:
                    try:
                        if b"\x00" in record.string:
                            name_str = record.string.decode("utf-16-be")
                        else:
                            name_str = record.string.decode("utf-8")
                        names[record.nameID] = name_str
                    except:
                        continue

            # Extract key information
            family = names.get(1, "Unknown")  # Font Family
            subfamily = names.get(2, "Regular")  # Font Subfamily
            full_name = names.get(4, family + " " + subfamily)  # Full Name
            postscript_name = names.get(6, full_name)  # PostScript Name

            # Extract additional metadata
            version = names.get(5, "")
            trademark = names.get(7, "")
            manufacturer = names.get(8, "")
            designer = names.get(9, "")
            description = names.get(10, "")
            vendor_url = names.get(11, "")
            license_info = names.get(13, "")
            license_url = names.get(14, "")

            # Determine style
            is_bold = "bold" in subfamily.lower() or subfamily.lower() == "bold"
            is_italic = "italic" in subfamily.lower() or "oblique" in subfamily.lower()

            # Get weight from OS/2 table
            weight = 400
            try:
                os2_table = font.get("OS/2")
                if os2_table:
                    weight = os2_table.usWeightClass
            except:
                pass

            # Extract glyph information
            glyph_count = 0
            try:
                glyph_set = font.getGlyphSet()
                glyph_count = len(glyph_set)
            except:
                pass

            font_info = FontInfo(
                name=full_name,
                family=family,
                style=subfamily,
                weight=weight,
                is_italic=is_italic,
                is_bold=is_bold,
                source=FontSource.METADATA,
                confidence=1.0,
                file_path=font_path,
                format=Path(font_path).suffix.lower(),
                metadata={
                    "postscript_name": postscript_name,
                    "version": version,
                    "trademark": trademark,
                    "manufacturer": manufacturer,
                    "designer": designer,
                    "description": description,
                    "vendor_url": vendor_url,
                    "license": license_info,
                    "license_url": license_url,
                    "glyph_count": glyph_count,
                },
            )

            # Extract additional features
            font_info.features = self._extract_font_features(font)

            font.close()

            return font_info

        except Exception as e:
            logger.error(f"Error analyzing font file {font_path}: {e}")
            return FontInfo(
                name=Path(font_path).name,
                family="Unknown",
                source=FontSource.METADATA,
                confidence=0.0,
                file_path=font_path,
            )

    def _extract_font_features(self, font: "ttLib.TTFont") -> Dict[str, Any]:
        """Extract technical features from font."""
        features = {}

        try:
            # OS/2 table features
            os2 = font.get("OS/2")
            if os2:
                features["panose"] = list(os2.panose) if hasattr(os2, "panose") else []
                features["unicode_range"] = (
                    list(os2.ulUnicodeRange) if hasattr(os2, "ulUnicodeRange") else []
                )
                features["code_page_range"] = (
                    list(os2.ulCodePageRange1)
                    if hasattr(os2, "ulCodePageRange1")
                    else []
                )

            # Head table features
            head = font.get("head")
            if head:
                features["units_per_em"] = head.unitsPerEm
                features["created"] = (
                    str(head.created) if hasattr(head, "created") else ""
                )
                features["modified"] = (
                    str(head.modified) if hasattr(head, "modified") else ""
                )

            # Hhea table features
            hhea = font.get("hhea")
            if hhea:
                features["ascent"] = hhea.ascent
                features["descent"] = hhea.descent
                features["line_gap"] = hhea.lineGap

            # Post table features
            post = font.get("post")
            if post:
                features["italic_angle"] = post.italicAngle
                features["underline_position"] = post.underlinePosition
                features["underline_thickness"] = post.underlineThickness
                features["is_fixed_pitch"] = post.isFixedPitch

        except Exception as e:
            logger.debug(f"Error extracting font features: {e}")

        return features


class FontMatcher:
    """Match and compare fonts for similarity."""

    def __init__(self):
        self.feature_extractor = FontFeatureExtractor()

    def match_font(
        self, query_font: FontInfo, font_database: List[FontInfo]
    ) -> List[Tuple[FontInfo, float]]:
        """
        Find similar fonts in database.

        Returns list of (font, similarity_score) tuples sorted by similarity.
        """
        matches = []

        for font in font_database:
            similarity = self.compute_similarity(query_font, font)
            matches.append((font, similarity))

        # Sort by similarity (descending)
        matches.sort(key=lambda x: x[1], reverse=True)

        return matches

    def compute_similarity(self, font1: FontInfo, font2: FontInfo) -> float:
        """Compute similarity between two fonts."""
        scores = []

        # Name similarity (exact match or substring)
        if font1.family.lower() == font2.family.lower():
            scores.append(1.0)
        elif (
            font1.family.lower() in font2.family.lower()
            or font2.family.lower() in font1.family.lower()
        ):
            scores.append(0.8)
        else:
            scores.append(0.0)

        # Style similarity
        style_match = 1.0 if font1.style == font2.style else 0.5
        scores.append(style_match)

        # Weight similarity
        weight_diff = abs(font1.weight - font2.weight)
        weight_score = max(0, 1.0 - weight_diff / 400)
        scores.append(weight_score)

        # Italic/Bold match
        italic_match = 1.0 if font1.is_italic == font2.is_italic else 0.0
        bold_match = 1.0 if font1.is_bold == font2.is_bold else 0.0
        scores.extend([italic_match, bold_match])

        # Average score
        return sum(scores) / len(scores)

    def find_closest_font(
        self, query_font: FontInfo, font_database: List[FontInfo]
    ) -> Optional[Tuple[FontInfo, float]]:
        """Find the closest matching font in database."""
        matches = self.match_font(query_font, font_database)

        if matches:
            return matches[0]
        return None


class FontToImageGenerator:
    """
    Generate images using detected font characteristics.

    This class provides integration with AI image generation models
    to create images that replicate the detected font style.
    """

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")

    def generate_font_description(self, font_info: FontInfo) -> str:
        """
        Generate a detailed text description of the font for image generation.

        This description captures the visual characteristics of the font
        to guide AI image generation models.
        """
        descriptions = []

        # Basic font information
        descriptions.append(f"Font: {font_info.family} {font_info.style}")

        # Weight description
        if font_info.weight >= 700:
            descriptions.append("Bold, thick strokes")
        elif font_info.weight >= 600:
            descriptions.append("Semi-bold, moderately thick strokes")
        elif font_info.weight <= 300:
            descriptions.append("Light, thin strokes")
        else:
            descriptions.append("Regular weight strokes")

        # Style characteristics
        if font_info.is_italic:
            descriptions.append("Italic/slanted style")

        if font_info.is_bold:
            descriptions.append("Heavy, impactful appearance")

        # Features from metadata
        if font_info.features:
            if font_info.features.get("has_serif"):
                descriptions.append("Serif font with decorative strokes at letter ends")
            else:
                descriptions.append("Sans-serif font with clean, modern appearance")

            stroke_width = font_info.features.get("stroke_width", 0)
            if stroke_width > 3:
                descriptions.append("Thick, substantial letterforms")
            elif stroke_width < 1.5:
                descriptions.append("Thin, elegant letterforms")

        # Additional metadata
        if font_info.metadata:
            if font_info.metadata.get("description"):
                descriptions.append(f"Description: {font_info.metadata['description']}")

        return ". ".join(descriptions)

    def create_image_prompt(
        self, text: str, font_info: FontInfo, background: str = "white"
    ) -> str:
        """
        Create an optimized prompt for AI image generation.

        This creates a prompt that describes both the text content
        and the font style for accurate replication.
        """
        font_description = self.generate_font_description(font_info)

        prompt = f"""Create an image with the text "{text}" rendered in a font with these characteristics:
{font_description}

Requirements:
- Clean, high-quality text rendering
- {background} background
- Professional typography
- Sharp, clear letterforms
- Exact text: "{text}"
- No additional elements, just the text
"""
    #     prompt = f"""
    #     Generate the text 'My Sample Heading' using typography that closely matches the font 'Dancing Script' from the 'Dancing Script' family. Use a Regular Italic style with weight 400. The text should have a handwritten cursive script, connected flowing letterforms, elegant informal calligraphic feel, italic slant, regular weight. Preserve the visual personality of the reference font and avoid substituting it with a generic default font. Closest alternatives: Dancing Script, Pacifico, Allura Regular Italic. 
    # """

        return prompt

    def generate_image_with_font(
        self,
        text: str,
        font_info: FontInfo,
        output_path: str = "output.png",
        background: str = "white",
    ) -> Optional[str]:
        """
        Generate an image with text in the detected font style.

        This method:
        1. Creates a detailed prompt describing the font
        2. Calls an AI image generation API
        3. Saves the generated image

        Note: Requires API key for image generation service.
        """
        if not self.api_key:
            logger.warning(
                "No API key set for image generation. Set OPENAI_API_KEY environment variable."
            )
            return None

        try:
            prompt = self.create_image_prompt(text, font_info, background)

            # This is a placeholder for actual API integration
            # In practice, you would call the image generation API here
            logger.info(f"Generated prompt for image creation: {prompt[:100]}...")

            # Example API call (commented out):
            # response = requests.post(
            #     f"{self.api_base}/images/generations",
            #     headers={"Authorization": f"Bearer {self.api_key}"},
            #     json={
            #         "prompt": prompt,
            #         "n": 1,
            #         "size": "1024x1024"
            #     }
            # )
            #
            # if response.status_code == 200:
            #     image_url = response.json()['data'][0]['url']
            #     # Download and save image
            #     img_response = requests.get(image_url)
            #     with open(output_path, 'wb') as f:
            #         f.write(img_response.content)
            #     return output_path

            logger.info(
                "Image generation API integration placeholder - implement with your preferred AI service"
            )
            return None

        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None

    def render_text_locally(
        self,
        text: str,
        font_info: FontInfo,
        output_path: str = "output.png",
        font_size: int = 48,
        image_size: Tuple[int, int] = (800, 200),
        text_color: Tuple[int, int, int] = (0, 0, 0),
        bg_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Optional[str]:
        """
        Render text locally using PIL.

        This is a fallback method that renders text using system fonts
        when AI generation is not available.
        """
        try:
            from PIL import Image, ImageDraw, ImageFont

            # Create image
            image = Image.new("RGB", image_size, bg_color)
            draw = ImageDraw.Draw(image)

            # Try to find matching font file
            font_path = self._find_font_file(font_info)

            if font_path:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                except:
                    font = ImageFont.load_default()
            else:
                font = ImageFont.load_default()

            # Calculate text position (centered)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (image_size[0] - text_width) // 2
            y = (image_size[1] - text_height) // 2

            # Draw text
            draw.text((x, y), text, font=font, fill=text_color)

            # Save image
            image.save(output_path)
            logger.info(f"Text rendered and saved to {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"Error rendering text locally: {e}")
            return None

    def _find_font_file(self, font_info: FontInfo) -> Optional[str]:
        """Find font file matching the font info."""
        # This is a simplified implementation
        # In practice, you would search system font directories

        system_fonts_dirs = [
            "/usr/share/fonts",
            "/System/Library/Fonts",
            "C:/Windows/Fonts",
            os.path.expanduser("~/.fonts"),
        ]

        # Search for font file
        for font_dir in system_fonts_dirs:
            if os.path.exists(font_dir):
                for root, dirs, files in os.walk(font_dir):
                    for file in files:
                        if file.lower().endswith((".ttf", ".otf")):
                            if font_info.family.lower() in file.lower():
                                return os.path.join(root, file)

        return None


class UniversalFontDetector:
    """
    Main class for universal font detection.

    This class orchestrates font detection from various input formats
    and provides a unified interface for font analysis.
    """

    def __init__(self):
        self.pdf_extractor = PDFFontExtractor()
        self.image_extractor = ImageFontExtractor()
        self.docx_extractor = DOCXFontExtractor()
        self.presentation_extractor = PresentationFontExtractor()
        self.font_analyzer = FontFileAnalyzer()
        self.font_matcher = FontMatcher()
        self.image_generator = FontToImageGenerator()

        self.detected_fonts: List[FontInfo] = []
        self.font_database: List[FontInfo] = []

    def detect_fonts(self, file_path: str) -> List[FontInfo]:
        """
        Detect fonts from any supported file format.

        Args:
            file_path: Path to input file

        Returns:
            List of detected FontInfo objects
        """
        file_path = Path(file_path)
        effective_extension = file_path.suffix.lower()

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return []

        extension = file_path.suffix.lower()

        if extension in SUPPORTED_DOCUMENT_FORMATS:
            from format_validation import validate_document_format

            format_info = validate_document_format(file_path)
            detected_document_format = format_info.detected_format
            if detected_document_format in {
                "pdf",
                "docx",
                "doc",
                "pptx",
                "ppt",
                "odt",
                "rtf",
            }:
                effective_extension = f".{detected_document_format}"
            if format_info.warning:
                logger.warning(format_info.warning)

        logger.info(
            f"Processing file: {file_path} (format: {extension}, effective: {effective_extension})"
        )

        if effective_extension in TRIGGER_PRINT_FORMATS:
            print("font_detector.py is being triggered", flush=True)

        if effective_extension == ".pdf":
            self.detected_fonts = self.pdf_extractor.extract_fonts(str(file_path))
        elif effective_extension in SUPPORTED_IMAGE_FORMATS:
            self.detected_fonts = self.image_extractor.extract_fonts(str(file_path))
        elif effective_extension == ".docx":
            self.detected_fonts = self.docx_extractor.extract_fonts(str(file_path))
        elif effective_extension == ".pptx":
            self.detected_fonts = self.presentation_extractor.extract_fonts(
                str(file_path)
            )
        elif effective_extension in {".doc", ".ppt", ".odt", ".rtf"}:
            self.detected_fonts = self._detect_fonts_from_text_document(str(file_path))
        elif effective_extension in SUPPORTED_FONT_FORMATS:
            font_info = self.font_analyzer.analyze_font_file(str(file_path))
            self.detected_fonts = [font_info] if font_info else []
        else:
            logger.warning(f"Unsupported file format: {extension}")
            return []

        logger.info(f"Detected {len(self.detected_fonts)} font(s)")

        return self.detected_fonts

    def _detect_fonts_from_text_document(self, file_path: str) -> List[FontInfo]:
        """
        Extract font information from text-based or legacy documents.

        Note: These formats don't reliably expose embedded font metadata, so we return
        a placeholder indicating no embedded fonts were found.
        """
        from format_validation import convert_document_to_text, validate_document_format

        file_path_obj = Path(file_path)
        format_info = validate_document_format(file_path)

        if format_info.warning:
            logger.warning(f"Format warning: {format_info.warning}")

        text_content = convert_document_to_text(file_path)

        if not text_content:
            logger.warning(f"Could not extract text from {file_path_obj.suffix} file")
            return []

        logger.info(
            f"Extracted {len(text_content)} characters from {file_path_obj.suffix} document"
        )

        fonts = [
            FontInfo(
                name=f"{file_path_obj.stem}_Document_Font",
                family="Unknown (No embedded fonts)",
                style="Regular",
                source=FontSource.METADATA,
                confidence=0.1,
                metadata={
                    "document_type": file_path_obj.suffix.lstrip("."),
                    "char_count": len(text_content),
                    "text_sample": text_content[:200] if text_content else "",
                    "note": "ODT/RTF documents don't embed font metadata. "
                    "Visual font analysis may be needed for font identification.",
                },
            )
        ]

        return fonts

    def get_font_details(self, font_index: int = 0) -> Optional[Dict]:
        """Get detailed information about a specific font."""
        if 0 <= font_index < len(self.detected_fonts):
            return self.detected_fonts[font_index].to_dict()
        return None

    def find_similar_fonts(self, font_index: int = 0) -> List[Tuple[FontInfo, float]]:
        """Find similar fonts in the database."""
        if not self.detected_fonts:
            return []

        query_font = self.detected_fonts[font_index]
        return self.font_matcher.match_font(query_font, self.font_database)

    def generate_image_with_font(
        self,
        text: str,
        font_index: int = 0,
        output_path: str = "output.png",
        use_ai: bool = False,
    ) -> Optional[str]:
        """
        Generate an image with text in the detected font style.

        Args:
            text: Text to render
            font_index: Index of font to use
            output_path: Output image path
            use_ai: Whether to use AI image generation (requires API key)
        """
        if not self.detected_fonts:
            logger.error("No fonts detected. Run detect_fonts first.")
            return None

        font_info = self.detected_fonts[font_index]

        if use_ai:
            return self.image_generator.generate_image_with_font(
                text, font_info, output_path
            )
        else:
            return self.image_generator.render_text_locally(
                text, font_info, output_path
            )

    def export_results(self, output_path: str = "font_detection_results.json"):
        """Export detection results to JSON."""
        results = {
            "detected_fonts": [font.to_dict() for font in self.detected_fonts],
            "file_count": len(self.detected_fonts),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Results exported to {output_path}")

    def print_summary(self):
        """Print summary of detected fonts."""
        print("\n" + "=" * 60)
        print("FONT DETECTION SUMMARY")
        print("=" * 60)

        if not self.detected_fonts:
            print("No fonts detected.")
            return

        for i, font in enumerate(self.detected_fonts):
            print(f"\nFont #{i + 1}:")
            print(f"  Name: {font.name}")
            print(f"  Family: {font.family}")
            print(f"  Style: {font.style}")
            print(f"  Weight: {font.weight}")
            print(f"  Bold: {font.is_bold}, Italic: {font.is_italic}")
            print(f"  Source: {font.source.value}")
            print(f"  Confidence: {font.confidence:.2%}")

            if font.metadata:

                def convert_numpy(obj):
                    import numpy as np

                    if isinstance(obj, (np.integer,)):
                        return int(obj)
                    elif isinstance(obj, (np.floating,)):
                        return float(obj)
                    elif isinstance(obj, (np.ndarray,)):
                        return obj.tolist()
                    return str(obj)

                print(
                    f"  Metadata: {json.dumps(font.metadata, indent=4, default=convert_numpy)[:100]}..."
                )
                # print(f"  Metadata: {json.dumps(font.metadata, indent=4)[:100]}...")

        print("\n" + "=" * 60)


def main():
    """Main function for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Universal Font Detector - Detect fonts from PDF, images, documents, and font files"
    )
    parser.add_argument("input", help="Input file path (PDF, image, DOCX, TTF/OTF)")
    parser.add_argument(
        "-o",
        "--output",
        default="font_detection_results.json",
        help="Output JSON file path",
    )
    parser.add_argument("-t", "--text", help="Text to render with detected font")
    parser.add_argument(
        "-i",
        "--image-output",
        default="output.png",
        help="Output image path for text rendering",
    )
    parser.add_argument(
        "--ai", action="store_true", help="Use AI image generation (requires API key)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create detector
    detector = UniversalFontDetector()

    # Detect fonts
    fonts = detector.detect_fonts(args.input)

    if not fonts:
        print("No fonts detected.")
        sys.exit(1)

    # Print summary
    detector.print_summary()

    # Export results
    detector.export_results(args.output)

    # Generate image if text provided
    if args.text:
        print(f"\nGenerating image with text: '{args.text}'")
        result = detector.generate_image_with_font(
            args.text, output_path=args.image_output, use_ai=args.ai
        )

        if result:
            print(f"Image saved to: {result}")
        else:
            print("Failed to generate image")


if __name__ == "__main__":
    main()
