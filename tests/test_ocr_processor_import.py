from __future__ import annotations

import importlib
import sys


def test_ocr_processor_import_is_safe_without_google_credentials(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    sys.modules.pop("ocr_processor", None)
    module = importlib.import_module("ocr_processor")
    assert hasattr(module, "GoogleVisionOCRProcessor")

