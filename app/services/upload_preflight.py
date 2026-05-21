from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
import mimetypes
import zipfile

import pdfplumber
from PIL import Image
from pptx import Presentation

from app.core.config import get_settings
from app.core.exceptions import UploadValidationError
from app.utils.files import decode_base64_content, estimate_decoded_base64_size


@dataclass(slots=True)
class UploadPreflightResult:
    content: bytes
    normalized_mime_type: str
    detected_extension: str
    size_bytes: int
    page_count: int | None = None
    megapixels: float | None = None
    hints: dict[str, Any] | None = None


class UploadPreflightService:
    _allowed_extensions = {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".svg",
        ".ttf",
        ".otf",
        ".docx",
        ".pptx",
        ".txt",
        ".md",
        ".json",
        ".csv",
        ".tsv",
        ".doc",
        ".ppt",
    }
    _allowed_mime_types = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/svg+xml",
        "font/ttf",
        "font/otf",
        "application/x-font-ttf",
        "application/x-font-otf",
        "application/font-sfnt",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/msword",
        "application/vnd.ms-powerpoint",
        "text/plain",
        "text/markdown",
        "application/json",
        "text/csv",
        "text/tab-separated-values",
    }

    def __init__(self) -> None:
        self.settings = get_settings()

    def validate_base64_upload(
        self,
        *,
        filename: str,
        mime_type: str,
        content_base64: str,
    ) -> UploadPreflightResult:
        estimated_size = estimate_decoded_base64_size(content_base64)
        if estimated_size > self.settings.upload_max_file_bytes:
            raise UploadValidationError(
                f"{filename} exceeds the upload limit of {self.settings.upload_max_file_bytes // (1024 * 1024)} MB."
            )

        content = decode_base64_content(
            content_base64,
            max_bytes=self.settings.upload_max_file_bytes,
        )
        return self.validate_bytes(
            filename=filename,
            mime_type=mime_type,
            content=content,
        )

    def validate_bytes(
        self,
        *,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> UploadPreflightResult:
        extension = Path(filename).suffix.lower()
        normalized_mime = (mime_type or "").strip().lower() or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if extension not in self._allowed_extensions:
            raise UploadValidationError(f"{filename} is not a supported upload format.")
        if normalized_mime not in self._allowed_mime_types:
            raise UploadValidationError(f"{filename} uses an unsupported MIME type: {normalized_mime}.")

        page_count: int | None = None
        megapixels: float | None = None
        hints: dict[str, Any] = {}

        if extension == ".pdf":
            with pdfplumber.open(BytesIO(content)) as pdf:
                page_count = len(pdf.pages)
            if page_count > self.settings.upload_max_pdf_pages:
                raise UploadValidationError(
                    f"{filename} has {page_count} pages, which exceeds the PDF limit of {self.settings.upload_max_pdf_pages}."
                )
        elif extension in {".pptx", ".ppt"}:
            actual_extension = extension
            if extension == ".ppt":
                actual_extension = self._resolve_office_suffix(content, extension)
                if actual_extension != ".pptx":
                    raise UploadValidationError(
                        f"{filename} is a legacy PowerPoint file. Please upload PPTX instead."
                    )
            presentation = Presentation(BytesIO(content))
            page_count = len(presentation.slides)
            if page_count > self.settings.upload_max_presentation_pages:
                raise UploadValidationError(
                    f"{filename} has {page_count} slides, which exceeds the presentation limit of {self.settings.upload_max_presentation_pages}."
                )
            hints["resolved_extension"] = actual_extension
        elif extension in {".docx", ".doc"}:
            actual_extension = extension
            if extension == ".doc":
                actual_extension = self._resolve_office_suffix(content, extension)
                if actual_extension != ".docx":
                    raise UploadValidationError(
                        f"{filename} is a legacy Word file. Please upload DOCX instead."
                    )
            hints["resolved_extension"] = actual_extension
        elif extension in {".png", ".jpg", ".jpeg", ".webp"}:
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
            megapixels = (width * height) / 1_000_000
            if megapixels > float(self.settings.upload_max_image_megapixels):
                raise UploadValidationError(
                    f"{filename} is {megapixels:.1f} MP, which exceeds the image limit of {self.settings.upload_max_image_megapixels} MP."
                )
            hints["image_size"] = {"width": width, "height": height}
        elif extension == ".svg":
            hints["vector_image"] = True
        elif extension in {".ttf", ".otf"}:
            hints["font_asset"] = True

        return UploadPreflightResult(
            content=content,
            normalized_mime_type=normalized_mime,
            detected_extension=extension,
            size_bytes=len(content),
            page_count=page_count,
            megapixels=megapixels,
            hints=hints or None,
        )

    @staticmethod
    def _resolve_office_suffix(content: bytes, current_extension: str) -> str:
        if current_extension not in {".doc", ".ppt"}:
            return current_extension
        if not zipfile.is_zipfile(BytesIO(content)):
            return current_extension
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = archive.namelist()
        if any(name.startswith("word/") for name in names):
            return ".docx"
        if any(name.startswith("ppt/") for name in names):
            return ".pptx"
        return current_extension
