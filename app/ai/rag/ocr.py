from __future__ import annotations

import logging
from pathlib import Path
from time import sleep
from typing import Any
import zipfile

import pdfplumber

from app.core.config import get_settings
from ocr_processor import GoogleVisionOCRProcessor

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self) -> None:
        self.processor = GoogleVisionOCRProcessor()
        self.settings = get_settings()

    @staticmethod
    def _is_transient_ocr_error(exc: Exception) -> bool:
        message = str(exc).lower()
        transient_markers = (
            "failed to connect to all addresses",
            "endpoint closing",
            "unavailable",
            "service unavailable",
            "deadline exceeded",
            "connection reset",
            "temporarily unavailable",
            "connection error",
            "connect() timed out",
            "failed to connect to remote host",
            "tcp handshaker shutdown",
            "hostname lookup error",
            "address lookup failed",
            "dns server returned general failure",
            "domain name not found",
            "temporary failure in name resolution",
        )
        return any(marker in message for marker in transient_markers)

    @staticmethod
    def _is_authentication_ocr_error(exc: Exception) -> bool:
        message = str(exc).lower()
        authentication_markers = (
            "invalid authentication credentials",
            "expected oauth 2 access token",
            "could not automatically determine credentials",
            "google_application_credentials",
            "unauthenticated",
        )
        return any(marker in message for marker in authentication_markers)

    def _with_retry(
        self,
        operation_name: str,
        func,
        *args,
        skip_auth_errors: bool = False,
        **kwargs,
    ):
        attempts = max(int(self.settings.ocr_retry_attempts), 1)
        base_backoff = max(float(self.settings.ocr_retry_backoff_seconds), 0.0)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if skip_auth_errors and self._is_authentication_ocr_error(exc):
                    logger.warning(
                        "ocr.%s.skipped authentication_error=%s",
                        operation_name,
                        exc,
                    )
                    return None
                if attempt >= attempts or not self._is_transient_ocr_error(exc):
                    logger.error(
                        "ocr.%s.failed attempt=%s/%s transient=%s error=%s",
                        operation_name,
                        attempt,
                        attempts,
                        self._is_transient_ocr_error(exc),
                        exc,
                    )
                    raise
                delay_seconds = round(base_backoff * attempt, 2)
                logger.warning(
                    "ocr.%s.retry attempt=%s/%s delay_seconds=%s error=%s",
                    operation_name,
                    attempt,
                    attempts,
                    delay_seconds,
                    exc,
                )
                if delay_seconds > 0:
                    sleep(delay_seconds)
        if last_error:
            raise last_error

    @staticmethod
    def _resolve_office_suffix(file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()
        if suffix not in {".doc", ".ppt"}:
            return suffix
        try:
            if not zipfile.is_zipfile(file_path):
                return suffix
            with zipfile.ZipFile(file_path) as archive:
                names = archive.namelist()
            if any(name.startswith("word/") for name in names):
                return ".docx"
            if any(name.startswith("ppt/") for name in names):
                return ".pptx"
        except Exception:  # noqa: BLE001
            return suffix
        return suffix

    @staticmethod
    def _scratch_root(file_path: str) -> Path:
        return Path(file_path).parent / "_ocr"

    @staticmethod
    def _analysis_paths_for_images(image_paths: list[str]) -> list[str]:
        analysis_paths: list[str] = []
        for image_path in image_paths:
            candidate = Path(str(image_path)).with_name(f"{Path(str(image_path)).stem}_analysis.json")
            if candidate.exists():
                analysis_paths.append(str(candidate))
        return analysis_paths

    def extract_visual_candidates(self, file_path: str) -> list[str]:
        suffix = self._resolve_office_suffix(file_path)
        scratch_root = self._scratch_root(file_path)
        scratch_root.mkdir(parents=True, exist_ok=True)
        if suffix == ".pdf":
            output_dir = scratch_root / "page_images"
            output_dir.mkdir(parents=True, exist_ok=True)
            return [
                str(image_path)
                for image_path in self._with_retry(
                    "extract_images_only",
                    self.processor.extract_images_only,
                    file_path,
                    output_folder=str(output_dir),
                )
            ]
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return [file_path]
        return []

    def extract(self, file_path: str, progress_callback=None) -> dict[str, Any]:
        suffix = self._resolve_office_suffix(file_path)
        scratch_root = self._scratch_root(file_path)
        scratch_root.mkdir(parents=True, exist_ok=True)
        if suffix == ".pdf":
            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
            text = self._with_retry(
                "extract_text_from_pdf",
                self.processor.extract_text_from_pdf,
                file_path,
                output_dir=str(scratch_root),
                progress_callback=progress_callback,
            )
            page_images_dir = scratch_root / "page_images"
            page_images = (
                [str(path) for path in sorted(page_images_dir.glob("*.png"))]
                if page_images_dir.exists()
                else []
            )
            analysis_paths = self._analysis_paths_for_images(page_images)
            return {
                "text": text,
                "images": page_images,
                "analysis_paths": analysis_paths,
                "page_count": page_count,
                "source_format": "pdf",
            }
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            warnings: list[str] = []
            text = self._with_retry(
                "extract_text_from_image_file",
                self.processor.extract_text_from_image_file,
                file_path,
                output_dir=str(scratch_root),
                progress_callback=progress_callback,
                skip_auth_errors=True,
            )
            if text is None:
                warnings.append("Image text OCR was skipped because OCR provider authentication failed.")
            stored_image_path = self._with_retry(
                "save_and_analyze_image_file",
                self.processor.save_and_analyze_image_file,
                image_path=file_path,
                output_folder=str(scratch_root),
                skip_auth_errors=True,
            )
            analysis_path = None
            if stored_image_path:
                candidate_path = Path(str(stored_image_path)).with_name(
                    f"{Path(str(stored_image_path)).stem}_analysis.json"
                )
                if candidate_path.exists():
                    analysis_path = str(candidate_path)
                else:
                    warnings.append("Image visual analysis did not produce an analysis file.")
            else:
                warnings.append("Image visual analysis was skipped because OCR provider authentication failed.")
            payload = {
                "text": text or "",
                "images": [file_path],
                "page_count": 1,
                "source_format": suffix.lstrip("."),
                "warnings": warnings,
            }
            if analysis_path:
                payload["analysis_path"] = analysis_path
                payload["analysis_paths"] = [analysis_path]
            return payload
        if suffix in {".ttf", ".otf"}:
            return {"text": "", "images": [], "page_count": 0, "source_format": suffix.lstrip(".")}
        if suffix == ".pptx":
            payload = self._with_retry(
                "extract_text_and_images_from_pptx",
                self.processor.extract_text_and_images_from_pptx,
                file_path,
                output_dir=str(scratch_root),
                progress_callback=progress_callback,
            )
            images = payload.get("images", []) or []
            return {
                "text": payload.get("text", ""),
                "images": images,
                "analysis_paths": self._analysis_paths_for_images(images),
                "page_count": len(payload.get("slides", [])) or 1,
                "source_format": "pptx",
            }
        if suffix == ".docx":
            images = self._with_retry(
                "extract_images_from_docx",
                self.processor.extract_images_from_docx,
                file_path,
                output_dir=str(scratch_root),
                progress_callback=progress_callback,
            )
            return {
                "text": "",
                "images": images,
                "analysis_paths": self._analysis_paths_for_images(images),
                "page_count": 1,
                "source_format": "docx",
            }
        return {"text": "", "images": [], "page_count": 0, "source_format": suffix.lstrip(".")}
