from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import traceback
from typing import Any

from app.core.config import BASE_DIR, get_settings


class GenerationTraceService:
    BRAND_USAGE_DIRNAME = "Brand usage"
    READABLE_VISUAL_TRACE_DIRNAME = "readable_generation_traces"
    MOJIBAKE_TOKENS = (
        "Ãƒ",
        "Ã‚",
        "Ã¢â‚¬",
        "Ã¢â‚¬â„¢",
        "Ã¢â‚¬Å“",
        "Ã¢â‚¬â€",
        "Ã¢â‚¬â€œ",
        "Ã¢â‚¬Â¢",
        "â€",
        "â€™",
        "â€œ",
        "â€\u009d",
        "â€“",
        "â€¢",
    )

    MOJIBAKE_TOKENS = MOJIBAKE_TOKENS + (
        "â€™",
        "â€œ",
        "â€\u009d",
        "â€“",
        "â€”",
        "â€¢",
    )

    def __init__(self, base_dir: str | Path | None = None, enabled: bool | None = None) -> None:
        settings = get_settings()
        self.enabled = settings.generation_trace_enabled if enabled is None else enabled
        resolved_base = base_dir or settings.generation_trace_base_path
        self.base_dir = Path(resolved_base)
        self.readable_visual_trace_base_dir = Path(settings.object_storage_base_path) / self.READABLE_VISUAL_TRACE_DIRNAME
        self.debug_log_paths = [
            self.base_dir / "_diagnostics" / "generation_trace_debug.jsonl",
            BASE_DIR / "log" / "generation_trace_debug.jsonl",
        ]

    def _write_debug_record(self, event: str, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "payload": payload,
        }
        serialized = json.dumps(record, ensure_ascii=False, default=str)
        for path in self.debug_log_paths:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(serialized)
                    handle.write("\n")
            except Exception:
                continue

    def write_debug_event(self, event: str, payload: dict[str, Any] | None = None) -> None:
        self._write_debug_record(
            event,
            {
                "enabled": self.enabled,
                "base_dir": str(self.base_dir),
                **(payload or {}),
            },
        )

    @classmethod
    def _repair_encoding_noise(cls, value: str) -> str:
        text = value or ""
        if not any(token in text for token in cls.MOJIBAKE_TOKENS):
            return text
        for source_encoding in ("cp1252", "latin-1"):
            try:
                repaired = text.encode(source_encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if repaired:
                return repaired
        replacements = {
            "â€™": "'",
            "â€œ": '"',
            "â€\u009d": '"',
            "â€“": "-",
            "â€”": "-",
            "â€¢": "-",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text

    @classmethod
    def _sanitize_payload(cls, payload: Any) -> Any:
        if isinstance(payload, str):
            return cls._repair_encoding_noise(payload)
        if isinstance(payload, dict):
            return {
                key: cls._sanitize_payload(value)
                for key, value in payload.items()
            }
        if isinstance(payload, list):
            return [cls._sanitize_payload(item) for item in payload]
        if isinstance(payload, tuple):
            return [cls._sanitize_payload(item) for item in payload]
        return payload

    @staticmethod
    def _slug(value: str, limit: int = 56) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip()).strip("-").lower()
        return normalized[:limit] or "generation"

    def start_trace(
        self,
        *,
        prompt: str,
        tenant_id: Any,
        brand_space_id: Any,
        session_id: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, str] | None:
        if not self.enabled:
            self.write_debug_event(
                "trace.start.skipped",
                {
                    "reason": "disabled",
                    "prompt_preview": str(prompt or "")[:160],
                    "tenant_id": str(tenant_id),
                    "brand_space_id": str(brand_space_id),
                    "session_id": str(session_id) if session_id else None,
                    "metadata": metadata or {},
                },
            )
            return None
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        trace_id = f"{timestamp}-{self._slug(prompt)}"
        trace_dir = self.base_dir / trace_id
        manifest = {
            "trace_id": trace_id,
            "timestamp": timestamp,
            "prompt": prompt,
            "tenant_id": str(tenant_id),
            "brand_space_id": str(brand_space_id),
            "session_id": str(session_id) if session_id else None,
            "metadata": metadata or {},
        }
        try:
            trace_dir.mkdir(parents=True, exist_ok=True)
            self.write_payload(trace_id, "manifest", manifest)
        except Exception as exc:
            self.write_debug_event(
                "trace.start.failed",
                {
                    "trace_id": trace_id,
                    "trace_dir": str(trace_dir),
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                    "prompt_preview": str(prompt or "")[:160],
                    "tenant_id": str(tenant_id),
                    "brand_space_id": str(brand_space_id),
                    "session_id": str(session_id) if session_id else None,
                    "metadata": metadata or {},
                },
            )
            return None
        self.write_debug_event(
            "trace.start.succeeded",
            {
                "trace_id": trace_id,
                "trace_dir": str(trace_dir),
                "manifest_written": True,
                "prompt_preview": str(prompt or "")[:160],
                "tenant_id": str(tenant_id),
                "brand_space_id": str(brand_space_id),
                "session_id": str(session_id) if session_id else None,
                "metadata": metadata or {},
            },
        )
        return {"trace_id": trace_id, "trace_dir": str(trace_dir)}

    def trace_dir(self, trace_id: str) -> Path:
        return self.base_dir / str(trace_id)

    def brand_usage_dir(self) -> Path:
        return self.base_dir / self.BRAND_USAGE_DIRNAME

    def readable_visual_trace_dir(self, trace_id: str) -> Path:
        return self.readable_visual_trace_base_dir / str(trace_id)

    def _write_json_file(self, file_path: Path, payload: Any) -> str | None:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            sanitized_payload = self._sanitize_payload(payload)
            file_path.write_text(
                json.dumps(sanitized_payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            self.write_debug_event(
                "trace.write_json.failed",
                {
                    "target": str(file_path),
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                },
            )
            return None
        return str(file_path)

    def _write_text_file(self, file_path: Path, text: str) -> str | None:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            sanitized_text = self._repair_encoding_noise(str(text or "").strip())
            file_path.write_text(sanitized_text, encoding="utf-8")
        except Exception as exc:
            self.write_debug_event(
                "trace.write_text.failed",
                {
                    "target": str(file_path),
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                },
            )
            return None
        return str(file_path)

    def write_payload(self, trace_id: str | None, filename: str, payload: Any) -> str | None:
        if not self.enabled or not trace_id:
            if trace_id:
                self.write_debug_event(
                    "trace.write_payload.skipped",
                    {"trace_id": trace_id, "filename": filename, "reason": "disabled"},
                )
            return None
        target = self.trace_dir(trace_id)
        file_path = target / f"{filename}.json"
        written = self._write_json_file(file_path, payload)
        if written is None:
            self.write_debug_event(
                "trace.write_payload.failed",
                {
                    "trace_id": trace_id,
                    "filename": filename,
                    "target": str(file_path),
                },
            )
            return None
        return written

    def append_event(self, trace_id: str | None, event: str, payload: Any | None = None) -> str | None:
        if not self.enabled or not trace_id:
            return None
        target = self.trace_dir(trace_id)
        file_path = target / "events.jsonl"
        record = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "payload": self._sanitize_payload(payload or {}),
        }
        try:
            target.mkdir(parents=True, exist_ok=True)
            with file_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str))
                handle.write("\n")
        except Exception as exc:
            self.write_debug_event(
                "trace.append_event.failed",
                {
                    "trace_id": trace_id,
                    "event_name": event,
                    "target": str(file_path),
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                },
            )
            return None
        return str(file_path)

    @staticmethod
    def _has_meaningful_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, dict):
            return any(GenerationTraceService._has_meaningful_value(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(GenerationTraceService._has_meaningful_value(item) for item in value)
        return True

    @classmethod
    def _value_preview(cls, value: Any, *, limit: int = 180) -> Any:
        if isinstance(value, str):
            text = " ".join(value.split())
            return text[:limit].rstrip(" ,.;:") if len(text) > limit else text
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, dict):
            preview: dict[str, Any] = {}
            for key, item in value.items():
                if cls._is_technical_key(str(key)):
                    continue
                if not cls._has_meaningful_value(item):
                    continue
                preview[str(key)] = cls._value_preview(item, limit=limit)
                if len(preview) >= 4:
                    break
            return preview
        if isinstance(value, (list, tuple, set)):
            items: list[Any] = []
            for item in value:
                if not cls._has_meaningful_value(item):
                    continue
                items.append(cls._value_preview(item, limit=96))
                if len(items) >= 4:
                    break
            return items
        return str(value)

    @classmethod
    def _collect_field_previews(
        cls,
        value: Any,
        *,
        prefix: str = "",
        limit: int = 18,
    ) -> list[dict[str, Any]]:
        if limit <= 0 or not cls._has_meaningful_value(value):
            return []
        records: list[dict[str, Any]] = []

        def visit(candidate: Any, path: str) -> None:
            if len(records) >= limit or not cls._has_meaningful_value(candidate):
                return
            if isinstance(candidate, dict):
                for key, item in candidate.items():
                    next_path = f"{path}.{key}" if path else str(key)
                    visit(item, next_path)
                    if len(records) >= limit:
                        break
                return
            if isinstance(candidate, (list, tuple, set)):
                if not candidate:
                    return
                scalar_items = [
                    item
                    for item in candidate
                    if not isinstance(item, (dict, list, tuple, set)) and cls._has_meaningful_value(item)
                ]
                if scalar_items:
                    records.append(
                        {
                            "field": path or "value",
                            "value_preview": cls._value_preview(list(scalar_items), limit=120),
                        }
                    )
                    return
                for index, item in enumerate(candidate):
                    next_path = f"{path}[{index}]" if path else f"[{index}]"
                    visit(item, next_path)
                    if len(records) >= limit:
                        break
                return
            records.append(
                {
                    "field": path or "value",
                    "value_preview": cls._value_preview(candidate, limit=160),
                }
            )

        visit(value, prefix)
        return records

    @classmethod
    def _value_at_path(cls, value: Any, path: str) -> Any:
        current = value
        for match in re.finditer(r"([^[.\]]+)|\[(\d+)\]", str(path or "")):
            dict_key = match.group(1)
            list_index = match.group(2)
            if dict_key is not None:
                if not isinstance(current, dict) or dict_key not in current:
                    return None
                current = current.get(dict_key)
                continue
            if list_index is not None:
                index = int(list_index)
                if not isinstance(current, (list, tuple)) or index >= len(current):
                    return None
                current = current[index]
        return current

    @classmethod
    def _collect_path_previews(
        cls,
        value: Any,
        paths: list[str],
        *,
        limit: int = 18,
    ) -> list[dict[str, Any]]:
        previews: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_path in paths:
            path = str(raw_path or "").strip()
            if not path or path in seen:
                continue
            if cls._path_is_technical(path):
                continue
            seen.add(path)
            resolved = value if path == "value" else cls._value_at_path(value, path)
            if not cls._has_meaningful_value(resolved):
                continue
            previews.append(
                {
                    "field": path,
                    "value_preview": cls._value_preview(resolved, limit=160),
                }
            )
            if len(previews) >= limit:
                break
        return previews

    @classmethod
    def _asset_summary(cls, asset: dict[str, Any]) -> dict[str, Any]:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        source_metadata = metadata.get("source_metadata") if isinstance(metadata.get("source_metadata"), dict) else {}
        normalized_metadata = metadata.get("normalized_metadata") if isinstance(metadata.get("normalized_metadata"), dict) else {}
        return {
            "asset_id": str(asset.get("asset_id") or asset.get("id") or ""),
            "asset_role": str(asset.get("asset_role") or asset.get("asset_kind") or ""),
            "label": (
                str(metadata.get("label") or "").strip()
                or str(source_metadata.get("label") or "").strip()
                or str(source_metadata.get("name") or "").strip()
                or str(normalized_metadata.get("label") or "").strip()
            ),
            "storage_path": str(asset.get("storage_path") or ""),
            "trust_level": str(asset.get("trust_level") or ""),
            "review_class": str(metadata.get("review_class") or asset.get("review_class") or ""),
            "review_status": str(metadata.get("review_status") or asset.get("review_status") or ""),
        }

    @classmethod
    def _asset_content_summary(cls, asset: dict[str, Any]) -> dict[str, Any]:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        source_metadata = metadata.get("source_metadata") if isinstance(metadata.get("source_metadata"), dict) else {}
        normalized_metadata = metadata.get("normalized_metadata") if isinstance(metadata.get("normalized_metadata"), dict) else {}
        summary = {
            "content_summary": (
                str(metadata.get("summary") or "").strip()
                or str(source_metadata.get("summary") or "").strip()
                or str(normalized_metadata.get("summary") or "").strip()
                or None
            ),
            "content_tags": [str(item).strip() for item in (metadata.get("tags") or []) if str(item).strip()][:6],
            "visual_role": str(asset.get("asset_role") or asset.get("asset_kind") or "").strip() or None,
        }
        return {key: value for key, value in summary.items() if cls._has_meaningful_value(value)}

    @staticmethod
    def _evidence(stage: str, artifact: str, usage_type: str, details: str | None = None) -> dict[str, Any]:
        payload = {
            "stage": stage,
            "artifact": artifact,
            "usage_type": usage_type,
        }
        if details:
            payload["details"] = details
        return payload

    @classmethod
    def _section_usage_evidence(
        cls,
        *,
        section_code: str,
        runtime_brand_context: dict[str, Any],
        compiled_context: dict[str, Any],
        planning_hints: dict[str, Any],
        template_context: dict[str, Any],
        reference_assets: list[dict[str, Any]],
        retrieved_knowledge: dict[str, list[dict[str, Any]]],
        logo_selection: dict[str, Any] | None,
        selected_template: dict[str, Any],
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        copy_brief = compiled_context.get("brand_copy_brief") if isinstance(compiled_context.get("brand_copy_brief"), dict) else {}
        visual_brief = compiled_context.get("brand_visual_brief") if isinstance(compiled_context.get("brand_visual_brief"), dict) else {}
        audience_brief = compiled_context.get("audience_brief") if isinstance(compiled_context.get("audience_brief"), dict) else {}
        objective_brief = compiled_context.get("objective_brief") if isinstance(compiled_context.get("objective_brief"), dict) else {}
        prompt_intelligence_brief = (
            compiled_context.get("prompt_intelligence_brief")
            if isinstance(compiled_context.get("prompt_intelligence_brief"), dict)
            else {}
        )
        reference_family_profile = (
            compiled_context.get("reference_family_profile")
            if isinstance(compiled_context.get("reference_family_profile"), dict)
            else {}
        )
        template_fit_brief = (
            compiled_context.get("template_fit_brief")
            if isinstance(compiled_context.get("template_fit_brief"), dict)
            else {}
        )
        content_plan = compiled_context.get("content_plan") if isinstance(compiled_context.get("content_plan"), dict) else {}
        visual_plan = compiled_context.get("visual_plan") if isinstance(compiled_context.get("visual_plan"), dict) else {}

        if section_code in {"identity", "foundations", "voice_tone", "guardrails"} and cls._has_meaningful_value(copy_brief):
            evidence.append(
                cls._evidence(
                    "content_creation",
                    "compiled_context.brand_copy_brief",
                    "derived_context",
                    "Copy guidance is compiled from this section for downstream text generation.",
                )
            )
        if section_code in {"personas", "knowledge"} and cls._has_meaningful_value(audience_brief):
            evidence.append(
                cls._evidence(
                    "planning",
                    "compiled_context.audience_brief",
                    "derived_context",
                    "Audience and persona guidance is compiled before strategy and copy planning.",
                )
            )
        if section_code == "personas" and cls._has_meaningful_value(copy_brief):
            evidence.append(
                cls._evidence(
                    "tone_alignment",
                    "compiled_context.brand_copy_brief",
                    "derived_context",
                    "Persona goals, objections, and language preferences shape copy direction.",
                )
            )
        if section_code == "objectives" and cls._has_meaningful_value(objective_brief):
            evidence.append(
                cls._evidence(
                    "cta_generation",
                    "compiled_context.objective_brief",
                    "derived_context",
                    "Objective configuration informs the CTA and conversion bias.",
                )
            )
        if section_code == "prompt_intelligence" and cls._has_meaningful_value(prompt_intelligence_brief):
            evidence.append(
                cls._evidence(
                    "planning",
                    "compiled_context.prompt_intelligence_brief",
                    "derived_context",
                    "Platform-specific prompt guidance is compiled from prompt intelligence.",
                )
            )
            evidence.append(
                cls._evidence(
                    "content_creation",
                    "compiled_context.prompt_intelligence_brief",
                    "derived_context",
                    "Prompt starters and platform rules guide copy framing.",
                )
            )
        if section_code in {"visual_identity", "identity"} and cls._has_meaningful_value(visual_brief):
            evidence.append(
                cls._evidence(
                    "visual_direction",
                    "compiled_context.brand_visual_brief",
                    "derived_context",
                    "Visual brand rules are compiled before layout and rendering.",
                )
            )
        if section_code == "visual_identity" and cls._has_meaningful_value(reference_family_profile):
            evidence.append(
                cls._evidence(
                    "carousel_structure",
                    "compiled_context.reference_family_profile",
                    "derived_context",
                    "Reference family and sequencing guidance influence multi-slide structure when present.",
                )
            )
        if section_code == "visual_identity" and cls._has_meaningful_value(template_fit_brief):
            evidence.append(
                cls._evidence(
                    "layout_generation",
                    "compiled_context.template_fit_brief",
                    "derived_context",
                    "Template-fit and layout DNA are evaluated against visual identity.",
                )
            )
        if section_code == "visual_identity" and cls._has_meaningful_value(selected_template):
            evidence.append(
                cls._evidence(
                    "template_selection",
                    "selected_template",
                    "selection_output",
                    "A template was selected or planned for this generation.",
                )
            )
        if section_code == "visual_identity" and cls._has_meaningful_value(template_context):
            evidence.append(
                cls._evidence(
                    "layout_generation",
                    "template_context",
                    "direct_pass_through",
                    "Template metadata and editable zones are available to the orchestrator.",
                )
            )
        if section_code == "visual_identity" and cls._has_meaningful_value(reference_assets):
            evidence.append(
                cls._evidence(
                    "image_generation",
                    "reference_assets",
                    "direct_pass_through",
                    "Approved reference visuals are passed into the orchestrator.",
                )
            )
        if section_code == "visual_identity" and cls._has_meaningful_value(visual_plan):
            evidence.append(
                cls._evidence(
                    "styling",
                    "compiled_context.visual_plan",
                    "derived_context",
                    "Visual plan instructions are prepared before scene-graph and render steps.",
                )
            )
        if section_code in {"identity", "visual_identity"} and cls._has_meaningful_value(logo_selection):
            evidence.append(
                cls._evidence(
                    "render_preparation",
                    "logo_selection",
                    "selection_output",
                    "The resolved logo selection is prepared for render or export.",
                )
            )
        if section_code in {"guardrails", "identity", "foundations", "voice_tone", "visual_identity", "prompt_intelligence"} and cls._has_meaningful_value(planning_hints):
            evidence.append(
                cls._evidence(
                    "planning",
                    "planning_hints",
                    "derived_context",
                    "The layout decision phase runs after the brand context is resolved.",
                )
            )
        if section_code == "knowledge" and any(retrieved_knowledge.get(channel) for channel in retrieved_knowledge):
            evidence.append(
                cls._evidence(
                    "planning",
                    "retrieved_knowledge",
                    "external_retrieval",
                    "Knowledge retrieval returned supporting material for the prompt.",
                )
            )
        if section_code == "knowledge" and cls._has_meaningful_value(content_plan):
            evidence.append(
                cls._evidence(
                    "content_creation",
                    "compiled_context.content_plan",
                    "derived_context",
                    "Retrieved knowledge can influence the content plan when available.",
                )
            )
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in evidence:
            key = f"{item.get('stage')}::{item.get('artifact')}::{item.get('usage_type')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _source_access_summary(input_access_summary: dict[str, Any], source_name: str) -> dict[str, Any]:
        source_summary = input_access_summary.get(source_name)
        return source_summary if isinstance(source_summary, dict) else {}

    @staticmethod
    def _relative_access_paths(paths: list[str], prefix: str) -> list[str]:
        relative: list[str] = []
        normalized_prefix = str(prefix or "").strip()
        dotted_prefix = f"{normalized_prefix}."
        for path in paths:
            text = str(path or "").strip()
            if not text:
                continue
            if text == normalized_prefix:
                relative.append(normalized_prefix)
            elif text.startswith(dotted_prefix):
                relative.append(text[len(dotted_prefix):])
        return relative

    @classmethod
    def _section_access_snapshot(
        cls,
        *,
        section_code: str,
        input_access_summary: dict[str, Any],
    ) -> dict[str, Any]:
        if section_code == "personas":
            source_summary = cls._source_access_summary(input_access_summary, "persona_context")
            return {
                "used_paths": list(source_summary.get("used_paths") or []),
                "unused_paths": list(source_summary.get("unused_paths") or []),
                "read_counts": dict(source_summary.get("read_counts") or {}),
                "access_types": dict(source_summary.get("access_types") or {}),
                "events": list(source_summary.get("events") or []),
            }
        if section_code == "objectives":
            source_summary = cls._source_access_summary(input_access_summary, "objective_context")
            return {
                "used_paths": list(source_summary.get("used_paths") or []),
                "unused_paths": list(source_summary.get("unused_paths") or []),
                "read_counts": dict(source_summary.get("read_counts") or {}),
                "access_types": dict(source_summary.get("access_types") or {}),
                "events": list(source_summary.get("events") or []),
            }

        source_summary = cls._source_access_summary(input_access_summary, "brand_context")
        used_paths = cls._relative_access_paths(list(source_summary.get("used_paths") or []), section_code)
        unused_paths = cls._relative_access_paths(list(source_summary.get("unused_paths") or []), section_code)
        read_counts = {
            path[len(section_code) + 1:] if path.startswith(f"{section_code}.") else path: count
            for path, count in dict(source_summary.get("read_counts") or {}).items()
            if path == section_code or path.startswith(f"{section_code}.")
        }
        access_types = {
            path[len(section_code) + 1:] if path.startswith(f"{section_code}.") else path: value
            for path, value in dict(source_summary.get("access_types") or {}).items()
            if path == section_code or path.startswith(f"{section_code}.")
        }
        events = [
            {
                **event,
                "path": (
                    str(event.get("path") or "")[len(section_code) + 1:]
                    if str(event.get("path") or "").startswith(f"{section_code}.")
                    else event.get("path")
                ),
            }
            for event in list(source_summary.get("events") or [])
            if str(event.get("path") or "") == section_code or str(event.get("path") or "").startswith(f"{section_code}.")
        ]
        return {
            "used_paths": used_paths,
            "unused_paths": unused_paths,
            "read_counts": read_counts,
            "access_types": access_types,
            "events": events,
        }

    @classmethod
    def build_brand_usage_report(
        cls,
        *,
        trace_id: str,
        mode: str,
        prompt: str,
        tenant_id: Any,
        brand_space_id: Any,
        studio_panel: dict[str, Any],
        section_payloads: dict[str, Any],
        runtime_brand_context: dict[str, Any],
        persona_context: dict[str, Any] | None = None,
        objective_context: dict[str, Any] | None = None,
        reference_assets: list[dict[str, Any]] | None = None,
        template_candidates: list[dict[str, Any]] | None = None,
        template_context: dict[str, Any] | None = None,
        retrieved_knowledge: dict[str, list[dict[str, Any]]] | None = None,
        planning_hints: dict[str, Any] | None = None,
        explainability: dict[str, Any] | None = None,
        selected_template: dict[str, Any] | None = None,
        logo_candidates: list[dict[str, Any]] | None = None,
        logo_selection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        persona_context = persona_context if isinstance(persona_context, dict) else {}
        objective_context = objective_context if isinstance(objective_context, dict) else {}
        reference_assets = [item for item in (reference_assets or []) if isinstance(item, dict)]
        template_candidates = [item for item in (template_candidates or []) if isinstance(item, dict)]
        template_context = template_context if isinstance(template_context, dict) else {}
        if isinstance(retrieved_knowledge, dict):
            retrieved_knowledge = {
                str(channel): [item for item in items if isinstance(item, dict)]
                for channel, items in retrieved_knowledge.items()
            }
        else:
            retrieved_knowledge = {}
        planning_hints = planning_hints if isinstance(planning_hints, dict) else {}
        explainability = explainability if isinstance(explainability, dict) else {}
        selected_template = selected_template if isinstance(selected_template, dict) else {}
        compiled_context = explainability.get("compiled_context") if isinstance(explainability.get("compiled_context"), dict) else {}
        input_access_summary = (
            explainability.get("input_access_summary")
            if isinstance(explainability.get("input_access_summary"), dict)
            else {}
        )

        selected_reference_images = [
            cls._asset_summary(item)
            for item in (explainability.get("selected_reference_images") or [])
            if isinstance(item, dict)
        ]
        conditioning_reference_images = [
            cls._asset_summary(item)
            for item in (explainability.get("conditioning_reference_images") or [])
            if isinstance(item, dict)
        ]

        section_keys: list[str] = []
        ordered_keys = list(section_payloads.keys()) + list(runtime_brand_context.keys())
        if cls._has_meaningful_value(persona_context):
            ordered_keys.append("personas")
        if cls._has_meaningful_value(objective_context):
            ordered_keys.append("objectives")
        for key in ordered_keys:
            normalized = str(key or "").strip()
            if normalized and normalized not in section_keys:
                section_keys.append(normalized)

        brand_form_data: dict[str, Any] = {}
        for section_code in section_keys:
            if section_code == "personas":
                raw_section = section_payloads.get(section_code) or persona_context
            elif section_code == "objectives":
                raw_section = section_payloads.get(section_code) or objective_context
            else:
                raw_section = section_payloads.get(section_code) or runtime_brand_context.get(section_code)
            resolved_section = runtime_brand_context.get(section_code) if isinstance(runtime_brand_context, dict) else None
            evidence = cls._section_usage_evidence(
                section_code=section_code,
                runtime_brand_context=runtime_brand_context,
                compiled_context=compiled_context,
                planning_hints=planning_hints,
                template_context=template_context,
                reference_assets=reference_assets,
                retrieved_knowledge=retrieved_knowledge,
                logo_selection=logo_selection,
                selected_template=selected_template,
            )
            section_access = cls._section_access_snapshot(
                section_code=section_code,
                input_access_summary=input_access_summary,
            )
            section_available = cls._has_meaningful_value(raw_section)
            section_used = bool(evidence) or bool(section_access["used_paths"])
            used_field_previews = cls._collect_path_previews(raw_section, section_access["used_paths"])
            brand_form_data[section_code] = {
                "available": section_available,
                "used": section_used,
                "usage_status": (
                    "used"
                    if section_used
                    else "available_not_read"
                    if section_available
                    else "not_available"
                ),
                "source": {
                    "type": "postgresql.brand_configuration_sections"
                    if section_code not in {"personas", "objectives"}
                    else f"postgresql.{section_code}",
                    "section_code": section_code,
                },
                "what_specific_data_is_being_used": used_field_previews or cls._collect_field_previews(raw_section, prefix=section_code),
                "available_field_previews": cls._collect_field_previews(raw_section, prefix=section_code),
                "raw_section_preview": cls._value_preview(raw_section, limit=220),
                "resolved_context_preview": cls._value_preview(resolved_section, limit=220),
                "actually_read_field_paths": section_access["used_paths"],
                "not_read_field_paths": section_access["unused_paths"],
                "field_read_counts": section_access["read_counts"],
                "field_access_types": section_access["access_types"],
                "micro_read_events": section_access["events"],
                "where_it_is_used": evidence,
                "when_it_is_used_in_pipeline": sorted(
                    {
                        *[item["stage"] for item in evidence],
                        *[
                            item.get("stage")
                            for item in section_access["events"]
                            if isinstance(item, dict) and item.get("stage")
                        ],
                    }
                ),
            }

        reference_access = cls._source_access_summary(input_access_summary, "reference_assets")
        template_context_access = cls._source_access_summary(input_access_summary, "template_context")
        template_candidate_access = cls._source_access_summary(input_access_summary, "template_candidates")
        knowledge_access = cls._source_access_summary(input_access_summary, "retrieved_knowledge")
        live_research_access = cls._source_access_summary(input_access_summary, "live_research")
        logo_candidate_access = cls._source_access_summary(input_access_summary, "logo_candidates")
        content_format_access = cls._source_access_summary(input_access_summary, "content_format_guide")

        template_usage = {
            "selected_template": {
                "template_id": str(selected_template.get("template_id") or selected_template.get("id") or ""),
                "template_name": str(selected_template.get("template_name") or selected_template.get("name") or ""),
                "selected_by_layout_mode": str(
                    (explainability.get("creative_decision") or explainability.get("layout_decision") or {}).get("layout_mode") or ""
                ),
            },
            "template_candidates": [
                {
                    "template_id": str(item.get("template_id") or ""),
                    "name": str(item.get("name") or ""),
                    "score": item.get("score"),
                    "match_type": str(item.get("match_type") or ""),
                    "decision_confidence": item.get("decision_confidence"),
                    "reasons": item.get("reasons") if isinstance(item.get("reasons"), list) else [],
                }
                for item in template_candidates[:5]
            ],
            "template_context_available": bool(template_context),
            "template_context_preview": cls._value_preview(template_context, limit=220),
            "actually_read_template_candidate_paths": list(template_candidate_access.get("used_paths") or []),
            "not_read_template_candidate_paths": list(template_candidate_access.get("unused_paths") or []),
            "template_candidate_read_counts": dict(template_candidate_access.get("read_counts") or {}),
            "actually_read_template_context_paths": list(template_context_access.get("used_paths") or []),
            "not_read_template_context_paths": list(template_context_access.get("unused_paths") or []),
            "template_context_read_counts": dict(template_context_access.get("read_counts") or {}),
            "where_it_is_used": [
                cls._evidence(
                    "template_selection",
                    "template_candidates",
                    "selection_input",
                    "Template recommendations are generated before orchestration.",
                )
            ]
            + (
                [
                    cls._evidence(
                        "layout_generation",
                        "template_context",
                        "direct_pass_through",
                        "Template zones and metadata are passed into the orchestrator.",
                    )
                ]
                if template_context
                else []
            )
            + (
                [
                    cls._evidence(
                        "layout_generation",
                        "compiled_context.template_fit_brief",
                        "derived_context",
                        "Template fit is summarized in the compiled context.",
                    )
                ]
                if cls._has_meaningful_value(compiled_context.get("template_fit_brief"))
                else []
            ),
            "when_it_is_used_in_pipeline": [
                "template_selection",
                *(["layout_generation"] if template_context or cls._has_meaningful_value(compiled_context.get("template_fit_brief")) else []),
            ],
        }

        knowledge_channels = {
            channel: {
                "match_count": len(items),
                "top_matches": [
                    {
                        "score": item.get("score"),
                        "content_preview": cls._value_preview(item.get("content"), limit=140),
                        "metadata_preview": cls._value_preview(item.get("metadata"), limit=120),
                    }
                    for item in items[:3]
                ],
            }
            for channel, items in retrieved_knowledge.items()
            if items
        }

        return {
            "trace_id": trace_id,
            "generated_at": datetime.now().isoformat(),
            "mode": mode,
            "prompt": prompt,
            "tenant_id": str(tenant_id),
            "brand_space_id": str(brand_space_id),
            "studio_panel": studio_panel,
            "sources_used": {
                "brand_form_data": brand_form_data,
                "reference_creatives_and_samples": {
                    "provided_reference_assets": [cls._asset_summary(asset) for asset in reference_assets],
                    "selected_reference_images": selected_reference_images,
                    "conditioning_reference_images": conditioning_reference_images,
                    "actually_read_reference_asset_paths": list(reference_access.get("used_paths") or []),
                    "not_read_reference_asset_paths": list(reference_access.get("unused_paths") or []),
                    "reference_asset_read_counts": dict(reference_access.get("read_counts") or {}),
                    "where_it_is_used": [
                        cls._evidence(
                            "planning",
                            "reference_assets",
                            "selection_input",
                            "Approved reference assets are prepared before orchestration.",
                        )
                    ]
                    + (
                        [
                            cls._evidence(
                                "image_generation",
                                "explainability.selected_reference_images",
                                "selection_output",
                                "The orchestrator selected reference images for visual grounding.",
                            )
                        ]
                        if selected_reference_images
                        else []
                    )
                    + (
                        [
                            cls._evidence(
                                "image_generation",
                                "explainability.conditioning_reference_images",
                                "selection_output",
                                "The orchestrator conditioned image generation on these references.",
                            )
                        ]
                        if conditioning_reference_images
                        else []
                    ),
                    "when_it_is_used_in_pipeline": [
                        "planning",
                        *(["image_generation"] if selected_reference_images or conditioning_reference_images else []),
                    ],
                },
                "templates": template_usage,
                "postgresql_and_other_sources": {
                    "postgresql": {
                        "brand_space": {
                            "source": "postgresql.brand_spaces",
                            "used_for": ["base_brand_context", "brand_lifecycle_validation"],
                        },
                        "brand_configuration_sections": {
                            "source": "postgresql.brand_configuration_sections",
                            "count": len([key for key, value in section_payloads.items() if cls._has_meaningful_value(value)]),
                            "section_codes": [key for key, value in section_payloads.items() if cls._has_meaningful_value(value)],
                        },
                        "selected_persona": {
                            "source": "postgresql.personas",
                            "used": cls._has_meaningful_value(persona_context),
                            "preview": cls._value_preview(persona_context, limit=200),
                        },
                        "selected_objective": {
                            "source": "postgresql.objectives",
                            "used": cls._has_meaningful_value(objective_context),
                            "preview": cls._value_preview(objective_context, limit=200),
                        },
                        "template_candidates": {
                            "source": "postgresql.templates",
                            "count": len(template_candidates),
                            "actually_read_paths": list(template_candidate_access.get("used_paths") or []),
                            "not_read_paths": list(template_candidate_access.get("unused_paths") or []),
                        },
                        "logo_candidates": {
                            "source": "postgresql.reusable_brand_assets_or_logo_assets",
                            "count": len([item for item in (logo_candidates or []) if isinstance(item, dict)]),
                            "selected_logo_preview": cls._value_preview(logo_selection, limit=180),
                            "actually_read_paths": list(logo_candidate_access.get("used_paths") or []),
                            "not_read_paths": list(logo_candidate_access.get("unused_paths") or []),
                        },
                    },
                    "other_sources": {
                        "retrieved_knowledge": {
                            "source": "knowledge_retrieval",
                            "channels_used": knowledge_channels,
                            "actually_read_paths": list(knowledge_access.get("used_paths") or []),
                            "not_read_paths": list(knowledge_access.get("unused_paths") or []),
                        },
                        "live_research": {
                            "source": "live_research",
                            "used": cls._has_meaningful_value(explainability.get("live_research")),
                            "preview": cls._value_preview(explainability.get("live_research"), limit=200),
                            "actually_read_paths": list(live_research_access.get("used_paths") or []),
                            "not_read_paths": list(live_research_access.get("unused_paths") or []),
                        },
                        "content_format_guide": {
                            "source": "content_format_guide",
                            "used": cls._has_meaningful_value(compiled_context.get("content_format_brief")),
                            "preview": cls._value_preview(compiled_context.get("content_format_brief"), limit=180),
                            "actually_read_paths": list(content_format_access.get("used_paths") or []),
                            "not_read_paths": list(content_format_access.get("unused_paths") or []),
                        },
                    },
                },
            },
            "generation_outputs_observed": {
                "planning_hints": cls._value_preview(planning_hints, limit=220),
                "compiled_context_preview": {
                    "brand_copy_brief": cls._value_preview(compiled_context.get("brand_copy_brief"), limit=180),
                    "brand_visual_brief": cls._value_preview(compiled_context.get("brand_visual_brief"), limit=180),
                    "audience_brief": cls._value_preview(compiled_context.get("audience_brief"), limit=180),
                    "objective_brief": cls._value_preview(compiled_context.get("objective_brief"), limit=180),
                    "prompt_intelligence_brief": cls._value_preview(compiled_context.get("prompt_intelligence_brief"), limit=180),
                    "template_fit_brief": cls._value_preview(compiled_context.get("template_fit_brief"), limit=180),
                },
                "generation_trace": cls._value_preview(explainability.get("generation_trace"), limit=220),
                "render_authority": str(explainability.get("render_authority") or ""),
                "generation_path": str(explainability.get("generation_path") or ""),
            },
        }

    def write_brand_usage_report(self, trace_id: str | None, report: dict[str, Any]) -> str | None:
        if not self.enabled or not trace_id:
            return None
        self.write_payload(trace_id, "brand_usage_report", report)
        file_path = self.brand_usage_dir() / f"{trace_id}.json"
        written = self._write_json_file(file_path, report)
        if written is None:
            self.write_debug_event(
                "trace.write_brand_usage.failed",
                {
                    "trace_id": trace_id,
                    "target": str(file_path),
                },
            )
            return None
        self.write_debug_event(
            "trace.write_brand_usage.succeeded",
            {
                "trace_id": trace_id,
                "target": str(file_path),
            },
        )
        return written

    @staticmethod
    def _normalize_format_name(studio_panel: dict[str, Any] | None) -> str:
        return str((studio_panel or {}).get("format") or "").strip().lower() or "static"

    @staticmethod
    def _dedupe_preserve_order(values: list[Any], *, limit: int = 8) -> list[Any]:
        deduped: list[Any] = []
        seen: set[str] = set()
        for value in values:
            key = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else str(value)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(value)
            if len(deduped) >= limit:
                break
        return deduped

    @classmethod
    def _is_technical_key(cls, key: str) -> bool:
        text = str(key or "").strip().lower()
        if not text:
            return False
        exact_blocklist = {
            "asset_id",
            "template_id",
            "storage_path",
            "mime_type",
            "uploaded_from",
            "file_size_bytes",
            "preflight_hints",
            "preflight_page_count",
            "page_count",
            "source_metadata",
            "normalized_metadata",
            "logo_asset_id",
            "logo_asset_ids",
            "template_name",
        }
        if text in exact_blocklist:
            return True
        if text == "id" or text.endswith("_id") or text.endswith("_ids"):
            return True
        if text.endswith("_path") or text.endswith("_paths"):
            return True
        return False

    @classmethod
    def _path_is_technical(cls, path: str) -> bool:
        text = str(path or "").strip()
        if not text:
            return False
        parts = [part.rstrip("]") for part in re.split(r"[.\[]", text) if part]
        return any(cls._is_technical_key(part) for part in parts)

    @classmethod
    def _top_level_field_names(cls, paths: list[str], *, limit: int = 10) -> list[str]:
        field_names: list[str] = []
        seen: set[str] = set()
        for path in paths:
            text = str(path or "").strip()
            if not text:
                continue
            root = re.split(r"[.\[]", text, maxsplit=1)[0].strip()
            if not root or root in seen or cls._is_technical_key(root):
                continue
            seen.add(root)
            field_names.append(root)
            if len(field_names) >= limit:
                break
        return field_names

    @classmethod
    def _brand_data_used_summary(
        cls,
        *,
        runtime_brand_context: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        input_access_summary: dict[str, Any],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        brand_access = cls._source_access_summary(input_access_summary, "brand_context")
        for section_code, section_value in runtime_brand_context.items():
            if not isinstance(section_value, dict):
                continue
            used_paths = cls._relative_access_paths(list(brand_access.get("used_paths") or []), str(section_code))
            if not used_paths:
                continue
            used_previews = cls._collect_path_previews(section_value, used_paths, limit=6)
            summary[str(section_code)] = {
                "content_focus": cls._top_level_field_names(used_paths, limit=6),
                "content_used": [
                    {
                        "from": str(item.get("field") or "").strip() or None,
                        "content": item.get("value_preview"),
                    }
                    for item in used_previews
                    if cls._has_meaningful_value(item.get("value_preview"))
                ],
                "section_summary": cls._value_preview(section_value, limit=160),
            }

        persona_access = cls._source_access_summary(input_access_summary, "persona_context")
        persona_used_paths = list(persona_access.get("used_paths") or [])
        if persona_used_paths:
            summary["persona_context"] = {
                "content_focus": cls._top_level_field_names(persona_used_paths, limit=6),
                "content_used": [
                    {
                        "from": str(item.get("field") or "").strip() or None,
                        "content": item.get("value_preview"),
                    }
                    for item in cls._collect_path_previews(persona_context, persona_used_paths, limit=6)
                    if cls._has_meaningful_value(item.get("value_preview"))
                ],
                "section_summary": cls._value_preview(persona_context, limit=160),
            }

        objective_access = cls._source_access_summary(input_access_summary, "objective_context")
        objective_used_paths = list(objective_access.get("used_paths") or [])
        if objective_used_paths:
            summary["objective_context"] = {
                "content_focus": cls._top_level_field_names(objective_used_paths, limit=6),
                "content_used": [
                    {
                        "from": str(item.get("field") or "").strip() or None,
                        "content": item.get("value_preview"),
                    }
                    for item in cls._collect_path_previews(objective_context, objective_used_paths, limit=6)
                    if cls._has_meaningful_value(item.get("value_preview"))
                ],
                "section_summary": cls._value_preview(objective_context, limit=160),
            }
        return summary

    @classmethod
    def _form_data_used_summary(
        cls,
        *,
        prompt: str,
        studio_panel: dict[str, Any],
        request_payload: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
    ) -> dict[str, Any]:
        inheritance_policy = request_payload.get("inheritance_policy") if isinstance(request_payload.get("inheritance_policy"), dict) else {}
        active_inheritance = {
            key: value
            for key, value in inheritance_policy.items()
            if bool(value)
        }
        persona_summary = {
            "name": str(persona_context.get("name") or "").strip() or None,
            "role": str(persona_context.get("role") or "").strip() or None,
            "audience_goals": [
                str(item).strip()
                for item in ((persona_context.get("psychographics") or {}).get("goals") or persona_context.get("audience_goals") or [])
                if str(item).strip()
            ][:6],
            "objections": [
                str(item).strip()
                for item in ((persona_context.get("psychographics") or {}).get("objections") or [])
                if str(item).strip()
            ][:4],
        }
        objective_configuration = objective_context.get("configuration") if isinstance(objective_context.get("configuration"), dict) else {}
        objective_summary = {
            "name": str(objective_context.get("name") or "").strip() or None,
            "description": str(objective_context.get("description") or "").strip() or None,
            "content_type": str(objective_context.get("content_type") or "").strip() or None,
            "platform_scope": str(objective_context.get("platform_scope") or "").strip() or None,
            "market_positioning": str(objective_configuration.get("market_positioning") or "").strip() or None,
        }
        studio_settings_used = {
            "format": str(studio_panel.get("format") or "").strip() or None,
            "platform_preset": str(studio_panel.get("platform_preset") or "").strip() or None,
            "file_type": str(studio_panel.get("file_type") or "").strip() or None,
            "size": studio_panel.get("size") if isinstance(studio_panel.get("size"), dict) else {},
            "pinned_template_id": str(studio_panel.get("pinned_template_id") or "").strip() or None,
        }
        summary = {
            "requested_content": {
                "prompt": prompt,
                "original_user_prompt": str(request_payload.get("raw_user_prompt") or "").strip() or None,
                "rewrite_instruction": str(request_payload.get("rewrite_instruction") or "").strip() or None,
            },
            "generation_goal": {
                "request_mode": str(request_payload.get("request_mode") or "").strip() or None,
            },
            "brand_space_form_inputs_used": {
                "studio_settings_used": studio_settings_used,
                "selected_persona_used": persona_summary,
                "selected_objective_used": objective_summary,
            },
            "content_inheritance_used": [str(key).strip() for key in active_inheritance.keys() if str(key).strip()][:8],
        }
        return {key: value for key, value in summary.items() if cls._has_meaningful_value(value)}

    @classmethod
    def _sequence_pack_summary(cls, template_context: dict[str, Any]) -> dict[str, Any]:
        sequence_pack = template_context.get("sequence_pack") if isinstance(template_context.get("sequence_pack"), dict) else {}
        slides = [item for item in (sequence_pack.get("slides") or []) if isinstance(item, dict)]
        if not sequence_pack and not slides:
            return {}
        return {
            "slide_count": int(sequence_pack.get("slide_count") or len(slides) or 0) or None,
            "story_roles": cls._dedupe_preserve_order(
                [str(item.get("story_role") or "").strip() for item in slides if str(item.get("story_role") or "").strip()],
                limit=8,
            ),
            "headline_hints": cls._dedupe_preserve_order(
                [str(item.get("headline_hint") or "").strip() for item in slides if str(item.get("headline_hint") or "").strip()],
                limit=6,
            ),
            "sequence_cues": cls._dedupe_preserve_order(
                [str(item).strip() for item in (sequence_pack.get("sequence_cues") or []) if str(item).strip()],
                limit=8,
            ),
        }

    @classmethod
    def _template_sample_data_summary(
        cls,
        *,
        template_context: dict[str, Any],
        template_candidates: list[dict[str, Any]],
        reference_assets: list[dict[str, Any]],
        research_editorial_brief: dict[str, Any],
        explainability: dict[str, Any],
    ) -> dict[str, Any]:
        template_context = template_context if isinstance(template_context, dict) else {}
        layout_decision = explainability.get("layout_decision") if isinstance(explainability.get("layout_decision"), dict) else {}
        creative_decision = explainability.get("creative_decision") if isinstance(explainability.get("creative_decision"), dict) else {}
        sample_editorial_brief = (
            research_editorial_brief.get("sample_editorial_brief")
            if isinstance(research_editorial_brief.get("sample_editorial_brief"), dict)
            else {}
        )
        selected_reference_images = [
            cls._asset_content_summary(item)
            for item in (explainability.get("selected_reference_images") or [])
            if isinstance(item, dict)
        ]
        conditioning_reference_images = [
            cls._asset_content_summary(item)
            for item in (explainability.get("conditioning_reference_images") or [])
            if isinstance(item, dict)
        ]
        return {
            "layout_content_adapted": {
                "layout_mode": str(creative_decision.get("layout_mode") or "").strip() or None,
                "content_areas_used": [str(item).strip() for item in (template_context.get("editable_fields") or []) if str(item).strip()][:8],
                "sequence_shape": cls._sequence_pack_summary(template_context),
            },
            "sample_content_adapted": {
                "narrative_contract": str(research_editorial_brief.get("narrative_contract") or "").strip() or None,
                "ordered_story_beats": [str(item).strip() for item in (research_editorial_brief.get("ordered_story_beats") or []) if str(item).strip()][:8],
                "sample_story_roles": [str(item).strip() for item in (sample_editorial_brief.get("story_roles") or []) if str(item).strip()][:8],
                "sample_headline_patterns": [str(item).strip() for item in (sample_editorial_brief.get("headline_patterns") or []) if str(item).strip()][:6],
            },
            "reference_content_adapted": {
                "provided_reference_content": [cls._asset_content_summary(item) for item in reference_assets[:6] if isinstance(item, dict)],
                "selected_reference_images": selected_reference_images,
                "conditioning_reference_images": conditioning_reference_images,
            },
        }

    @classmethod
    def _validation_summary(cls, explainability: dict[str, Any]) -> dict[str, Any]:
        validation_report = explainability.get("validation_report") if isinstance(explainability.get("validation_report"), dict) else {}
        content_semantic = (
            explainability.get("content_semantic_validation")
            if isinstance(explainability.get("content_semantic_validation"), dict)
            else {}
        )
        issues = [
            {
                "severity": str(item.get("severity") or "").strip() or None,
                "rule_id": str(item.get("rule_id") or "").strip() or None,
                "message": str(item.get("message") or "").strip() or None,
            }
            for item in (validation_report.get("issues") or [])[:6]
            if isinstance(item, dict)
        ]
        return {
            "guardrails_applied": cls._value_preview(explainability.get("guardrails_applied"), limit=180),
            "scene_graph_validation": {
                "status": str(validation_report.get("status") or "").strip() or None,
                "summary": [str(item).strip() for item in (validation_report.get("summary") or []) if str(item).strip()][:8],
                "issue_count": len(validation_report.get("issues") or []),
                "issues": issues,
            },
            "content_semantic_validation": {
                "status": str(content_semantic.get("status") or "").strip() or None,
                "summary": [str(item).strip() for item in (content_semantic.get("summary") or []) if str(item).strip()][:6],
                "issues": [str(item).strip() for item in (content_semantic.get("issues") or []) if str(item).strip()][:6],
                "repair_attempts": explainability.get("content_semantic_repair_attempts"),
            },
        }

    @classmethod
    def _planning_strategy_output(cls, research_editorial_brief: dict[str, Any]) -> dict[str, Any]:
        outline = [
            {
                "title": str(item.get("title") or "").strip() or None,
                "role": str(item.get("role") or "").strip() or None,
                "description": str(item.get("description") or "").strip() or None,
            }
            for item in (research_editorial_brief.get("outline") or [])[:8]
            if isinstance(item, dict)
        ]
        return {
            "mode": str(research_editorial_brief.get("mode") or "").strip() or None,
            "format_family": str(research_editorial_brief.get("format_family") or "").strip() or None,
            "topic_focus": str(research_editorial_brief.get("topic_focus") or "").strip() or None,
            "angle": str(research_editorial_brief.get("angle") or "").strip() or None,
            "thesis": str(research_editorial_brief.get("thesis") or "").strip() or None,
            "reader_payoff": str(research_editorial_brief.get("reader_payoff") or "").strip() or None,
            "hook_strategy": str(research_editorial_brief.get("hook_strategy") or "").strip() or None,
            "preferred_slide_count": research_editorial_brief.get("preferred_slide_count"),
            "outline": outline,
            "research_guard": cls._value_preview(research_editorial_brief.get("research_guard"), limit=180),
        }

    @classmethod
    def _metadata_structure_summary(cls, metadata: dict[str, Any], format_name: str) -> dict[str, Any]:
        carousel_specs = [item for item in (metadata.get("carousel_slide_specs") or []) if isinstance(item, dict)]
        infographic_specs = [item for item in (metadata.get("infographic_section_specs") or []) if isinstance(item, dict)]
        static_panel_spec = metadata.get("static_panel_spec") if isinstance(metadata.get("static_panel_spec"), dict) else {}
        return {
            "format": format_name,
            "visual_direction": str(metadata.get("visual_direction") or "").strip() or None,
            "design_style": str(metadata.get("design_style") or "").strip() or None,
            "image_prompt": str(metadata.get("image_prompt") or "").strip() or None,
            "static_panel_spec": cls._value_preview(static_panel_spec, limit=200) if static_panel_spec else {},
            "carousel_slide_count": len(carousel_specs),
            "infographic_section_count": len(infographic_specs),
        }

    @classmethod
    def _content_generation_output(
        cls,
        *,
        content_plan: dict[str, Any],
        generated_payload: dict[str, Any],
        explainability: dict[str, Any],
        format_name: str,
    ) -> dict[str, Any]:
        metadata = generated_payload.get("metadata") if isinstance(generated_payload.get("metadata"), dict) else {}
        message_strategy = explainability.get("message_strategy") if isinstance(explainability.get("message_strategy"), dict) else {}
        return {
            "content_plan_used": {
                "format_family": str(content_plan.get("format_family") or "").strip() or None,
                "sequence_contract": str(content_plan.get("sequence_contract") or "").strip() or None,
                "sequence_expectation": str(content_plan.get("sequence_expectation") or "").strip() or None,
                "preferred_slide_count": content_plan.get("preferred_slide_count"),
                "carousel_archetype": str(content_plan.get("carousel_archetype") or "").strip() or None,
                "planning_rules": [str(item).strip() for item in (content_plan.get("planning_rules") or []) if str(item).strip()][:8],
                "story_outline": [
                    {
                        "title": str(item.get("title") or "").strip() or None,
                        "role": str(item.get("role") or "").strip() or None,
                    }
                    for item in (content_plan.get("story_outline") or [])[:8]
                    if isinstance(item, dict)
                ],
            },
            "message_strategy_used": cls._value_preview(message_strategy, limit=220),
            "generated_content_for_image": {
                "headline": str(generated_payload.get("headline") or "").strip() or None,
                "body": str(generated_payload.get("body") or "").strip() or None,
                "cta": str(generated_payload.get("cta") or "").strip() or None,
                "hashtags": [str(item).strip() for item in (generated_payload.get("hashtags") or []) if str(item).strip()][:8],
                "metadata_structure": cls._metadata_structure_summary(metadata, format_name),
            },
        }

    @classmethod
    def _scene_graph_asset_bindings(cls, scene_graph: dict[str, Any]) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = []
        for element in (scene_graph.get("elements") or []) if isinstance(scene_graph, dict) else []:
            if not isinstance(element, dict):
                continue
            asset = element.get("asset") if isinstance(element.get("asset"), dict) else {}
            if not asset and not element.get("visual_metadata"):
                continue
            payload = {
                "role": str(element.get("role") or element.get("element_type") or "").strip() or None,
                "asset_role": str(asset.get("asset_role") or "").strip() or None,
                "visual_idea": cls._value_preview(asset.get("notes"), limit=180),
                "visual_metadata": cls._value_preview(element.get("visual_metadata"), limit=180),
            }
            if cls._has_meaningful_value(payload):
                bindings.append(payload)
        return bindings[:12]

    @classmethod
    def _layout_planning_output(
        cls,
        *,
        planning_hints: dict[str, Any],
        blueprint_payload: dict[str, Any],
        explainability: dict[str, Any],
    ) -> dict[str, Any]:
        creative_decision = explainability.get("creative_decision") if isinstance(explainability.get("creative_decision"), dict) else {}
        zones = [item for item in (blueprint_payload.get("zones") or []) if isinstance(item, dict)]
        return {
            "layout_decision_used": {
                "mode": str(planning_hints.get("mode") or creative_decision.get("layout_mode") or "").strip() or None,
                "reasoning": [str(item).strip() for item in (creative_decision.get("reasoning") or planning_hints.get("rationale") or []) if str(item).strip()][:8],
                "asset_strategy": cls._value_preview(creative_decision.get("asset_strategy"), limit=220),
                "adaptations": cls._value_preview(creative_decision.get("adaptations"), limit=220),
                "review_flags": [str(item).strip() for item in (creative_decision.get("review_flags") or planning_hints.get("review_flags") or []) if str(item).strip()][:8],
            },
            "blueprint_used": {
                "layout_type": str(blueprint_payload.get("layout_type") or "").strip() or None,
                "source_mode": str(blueprint_payload.get("source_mode") or "").strip() or None,
                "layout_archetype": str(blueprint_payload.get("layout_archetype") or "").strip() or None,
                "zone_roles": [str(item.get("role") or "").strip() for item in zones if str(item.get("role") or "").strip()][:12],
                "image_zone_roles": [
                    str(item.get("role") or "").strip()
                    for item in (blueprint_payload.get("image_zones") or [])
                    if isinstance(item, dict) and str(item.get("role") or "").strip()
                ][:8],
                "brand_rules_applied": cls._value_preview(blueprint_payload.get("brand_rules_applied"), limit=220),
            },
        }

    @classmethod
    def _visual_content_used_summary(
        cls,
        *,
        visual_plan: dict[str, Any],
        reference_assets: list[dict[str, Any]],
        generated_payload: dict[str, Any],
        explainability: dict[str, Any],
        format_name: str,
    ) -> dict[str, Any]:
        metadata = generated_payload.get("metadata") if isinstance(generated_payload.get("metadata"), dict) else {}
        scene_graph = explainability.get("scene_graph") if isinstance(explainability.get("scene_graph"), dict) else {}
        infographic_sections = [item for item in (metadata.get("infographic_section_specs") or []) if isinstance(item, dict)]
        chart_graph_signals = []
        for section in infographic_sections[:6]:
            signal = {
                "section_role": str(section.get("section_role") or "").strip() or None,
                "stat_highlights": [str(item).strip() for item in (section.get("stat_highlights") or []) if str(item).strip()][:4],
                "claim_evidence_pairs": cls._value_preview(section.get("claim_evidence_pairs"), limit=160),
            }
            if cls._has_meaningful_value(signal):
                chart_graph_signals.append(signal)
        for element in (scene_graph.get("elements") or [])[:20]:
            if not isinstance(element, dict):
                continue
            role_text = str(element.get("role") or element.get("element_type") or "").strip().lower()
            if not role_text or not any(token in role_text for token in ("chart", "graph", "stat", "proof")):
                continue
            chart_graph_signals.append(
                {
                    "scene_graph_role": role_text,
                    "text": cls._value_preview(element.get("text"), limit=140),
                }
            )
        return {
            "visual_plan_used": {
                "format_family": str(visual_plan.get("format_family") or "").strip() or None,
                "primary_unit": str(visual_plan.get("primary_unit") or "").strip() or None,
                "density_target": str(visual_plan.get("density_target") or "").strip() or None,
                "preferred_slide_count": visual_plan.get("preferred_slide_count"),
                "page_strategy": str(visual_plan.get("page_strategy") or "").strip() or None,
                "execution_mode": str(visual_plan.get("execution_mode") or "").strip() or None,
                "visual_sequence_expectation": str(visual_plan.get("visual_sequence_expectation") or "").strip() or None,
            },
            "visual_content_used": {
                "provided_reference_content": [cls._asset_content_summary(item) for item in reference_assets[:6] if isinstance(item, dict)],
                "selected_reference_images": [
                    cls._asset_content_summary(item)
                    for item in (explainability.get("selected_reference_images") or [])
                    if isinstance(item, dict)
                ],
                "conditioning_reference_images": [
                    cls._asset_content_summary(item)
                    for item in (explainability.get("conditioning_reference_images") or [])
                    if isinstance(item, dict)
                ],
                "visual_elements_used": cls._scene_graph_asset_bindings(scene_graph),
                "graph_or_chart_content_used": cls._dedupe_preserve_order(chart_graph_signals, limit=8),
                "visual_direction": str(metadata.get("visual_direction") or "").strip() or None,
                "design_style": str(metadata.get("design_style") or "").strip() or None,
                "image_prompt": str(metadata.get("image_prompt") or "").strip() or None,
                "visual_explanation_mode": str(explainability.get("visual_explanation_mode") or "").strip() or None,
                "visual_explanation_need": str(explainability.get("visual_explanation_need") or "").strip() or None,
                "format": format_name,
            },
        }

    @classmethod
    def _slide_trace_output(
        cls,
        *,
        format_name: str,
        generated_payload: dict[str, Any],
        research_editorial_brief: dict[str, Any],
        content_plan: dict[str, Any],
        template_context: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = generated_payload.get("metadata") if isinstance(generated_payload.get("metadata"), dict) else {}
        sample_editorial_brief = (
            research_editorial_brief.get("sample_editorial_brief")
            if isinstance(research_editorial_brief.get("sample_editorial_brief"), dict)
            else {}
        )
        sequence_pack = template_context.get("sequence_pack") if isinstance(template_context.get("sequence_pack"), dict) else {}
        sequence_slides = [item for item in (sequence_pack.get("slides") or []) if isinstance(item, dict)]
        sample_hints_by_index = {
            int(item.get("slide_index") or index + 1): {
                "story_role": str(item.get("story_role") or "").strip() or None,
                "headline_hint": str(item.get("headline_hint") or "").strip() or None,
            }
            for index, item in enumerate(sequence_slides)
        }

        if format_name == "carousel":
            units = []
            for index, slide in enumerate((metadata.get("carousel_slide_specs") or [])[:12], start=1):
                if not isinstance(slide, dict):
                    continue
                units.append(
                    {
                        "slide_number": int(slide.get("slide_number") or index),
                        "slide_role": str(slide.get("slide_role") or slide.get("role") or "").strip() or None,
                        "headline": str(slide.get("headline") or "").strip() or None,
                        "supporting_line": str(slide.get("supporting_line") or "").strip() or None,
                        "body": str(slide.get("body") or "").strip() or None,
                        "body_points": [str(item).strip() for item in (slide.get("body_points") or []) if str(item).strip()][:4],
                        "proof_points": [str(item).strip() for item in (slide.get("proof_points") or []) if str(item).strip()][:4],
                        "stat_highlights": [str(item).strip() for item in (slide.get("stat_highlights") or []) if str(item).strip()][:4],
                        "visual_focus": str(slide.get("visual_focus") or "").strip() or None,
                        "transition_note": str(slide.get("transition_note") or "").strip() or None,
                        "cta": str(slide.get("cta") or "").strip() or None,
                        "adapted_sample_hint": sample_hints_by_index.get(int(slide.get("slide_number") or index), {}),
                    }
                )
            return {
                "unit_type": "slide",
                "source_samples_adapted": {
                    "narrative_contract": str(research_editorial_brief.get("narrative_contract") or "").strip() or None,
                    "ordered_story_beats": [str(item).strip() for item in (content_plan.get("ordered_story_beats") or []) if str(item).strip()][:8],
                    "sample_story_roles": [str(item).strip() for item in (sample_editorial_brief.get("story_roles") or []) if str(item).strip()][:8],
                    "carousel_archetype": str(content_plan.get("carousel_archetype") or "").strip() or None,
                    "carousel_slide_grammar": cls._value_preview(content_plan.get("carousel_slide_grammar"), limit=220),
                    "sequence_pack": cls._sequence_pack_summary(template_context),
                },
                "units": units,
            }

        if format_name == "infographic":
            sections = []
            for index, section in enumerate((metadata.get("infographic_section_specs") or [])[:12], start=1):
                if not isinstance(section, dict):
                    continue
                sections.append(
                    {
                        "section_number": int(section.get("section_number") or index),
                        "section_role": str(section.get("section_role") or "").strip() or None,
                        "section_label": str(section.get("section_label") or "").strip() or None,
                        "headline": str(section.get("headline") or "").strip() or None,
                        "body": str(section.get("body") or "").strip() or None,
                        "body_points": [str(item).strip() for item in (section.get("body_points") or []) if str(item).strip()][:4],
                        "proof_points": [str(item).strip() for item in (section.get("proof_points") or []) if str(item).strip()][:4],
                        "stat_highlights": [str(item).strip() for item in (section.get("stat_highlights") or []) if str(item).strip()][:4],
                        "visual_focus": str(section.get("visual_focus") or "").strip() or None,
                    }
                )
            return {
                "unit_type": "section",
                "source_samples_adapted": {
                    "narrative_contract": str(research_editorial_brief.get("narrative_contract") or "").strip() or None,
                    "sample_story_roles": [str(item).strip() for item in (sample_editorial_brief.get("story_roles") or []) if str(item).strip()][:8],
                    "sequence_pack": cls._sequence_pack_summary(template_context),
                },
                "units": sections,
            }

        static_panel_spec = metadata.get("static_panel_spec") if isinstance(metadata.get("static_panel_spec"), dict) else {}
        return {
            "unit_type": "panel",
            "source_samples_adapted": {
                "narrative_contract": str(research_editorial_brief.get("narrative_contract") or "").strip() or None,
                "sample_story_roles": [str(item).strip() for item in (sample_editorial_brief.get("story_roles") or []) if str(item).strip()][:8],
                "sequence_pack": cls._sequence_pack_summary(template_context),
            },
            "units": [
                {
                    "panel_goal": str(static_panel_spec.get("panel_goal") or "").strip() or None,
                    "dominant_message": str(static_panel_spec.get("dominant_message") or generated_payload.get("headline") or "").strip() or None,
                    "supporting_lines": [str(item).strip() for item in (static_panel_spec.get("supporting_lines") or []) if str(item).strip()][:4],
                    "proof_points": [str(item).strip() for item in (static_panel_spec.get("proof_points") or []) if str(item).strip()][:4],
                    "stat_highlights": [str(item).strip() for item in (static_panel_spec.get("stat_highlights") or []) if str(item).strip()][:4],
                    "visual_focus": str(static_panel_spec.get("visual_focus") or metadata.get("visual_direction") or "").strip() or None,
                    "cta_mode": str(static_panel_spec.get("cta_mode") or "").strip() or None,
                    "headline": str(generated_payload.get("headline") or "").strip() or None,
                    "body": str(generated_payload.get("body") or "").strip() or None,
                    "cta": str(generated_payload.get("cta") or "").strip() or None,
                }
            ],
        }

    @classmethod
    def _trim_for_llm(
        cls,
        value: Any,
        *,
        depth: int = 0,
        max_depth: int = 5,
        max_dict_keys: int = 8,
        max_list_items: int = 6,
        string_limit: int = 220,
    ) -> Any:
        if depth >= max_depth:
            return cls._value_preview(value, limit=string_limit)
        if isinstance(value, str):
            return cls._value_preview(value, limit=string_limit)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            trimmed: dict[str, Any] = {}
            count = 0
            for key, item in value.items():
                if not cls._has_meaningful_value(item):
                    continue
                trimmed[str(key)] = cls._trim_for_llm(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_dict_keys=max_dict_keys,
                    max_list_items=max_list_items,
                    string_limit=string_limit,
                )
                count += 1
                if count >= max_dict_keys:
                    break
            return trimmed
        if isinstance(value, (list, tuple, set)):
            items: list[Any] = []
            for item in list(value)[:max_list_items]:
                if not cls._has_meaningful_value(item):
                    continue
                items.append(
                    cls._trim_for_llm(
                        item,
                        depth=depth + 1,
                        max_depth=max_depth,
                        max_dict_keys=max_dict_keys,
                        max_list_items=max_list_items,
                        string_limit=string_limit,
                    )
                )
            return items
        return cls._value_preview(value, limit=string_limit)

    @classmethod
    def _client_summary_prompt_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return cls._trim_for_llm(payload, max_depth=5, max_dict_keys=8, max_list_items=6, string_limit=220)

    @staticmethod
    def _stage_title(stage_name: str) -> str:
        return str(stage_name or "").replace("_", " ").strip().title()

    @classmethod
    def _is_noise_text(cls, value: str) -> bool:
        text = str(value or "").strip()
        lowered = text.casefold()
        if not text:
            return True
        if any(token in lowered for token in ("http://", "https://", "localhost", "/api/", "token=")):
            return True
        if re.search(r"\.(png|jpg|jpeg|pdf|webp)\b", lowered):
            return True
        if lowered in {
            "reference_creative",
            "template",
            "hybrid",
            "image",
            "logo",
            "body",
            "headline",
            "review",
            "static",
            "panel",
            "medium",
            "single_page",
            "single_frame_composition",
            "adapted_template",
            "research_editorial",
            "personas",
            "identity",
            "knowledge",
            "template_files",
            "audience_type",
            "brand_description",
        }:
            return True
        return False

    @classmethod
    def _collect_client_text_fragments(
        cls,
        value: Any,
        *,
        limit: int = 8,
    ) -> list[str]:
        fragments: list[str] = []

        preferred_keys = (
            "strategy_output",
            "content_generation_output",
            "layout_planning_output",
            "visual_content_used_for_image_generation",
            "slide_or_section_trace",
            "visual_content_used",
            "units",
            "prompt",
            "brand_description",
            "brand_name",
            "audience_type",
            "research_summary",
            "summary",
            "style_summary",
            "structure_summary",
            "content_summary",
            "headline",
            "body",
            "cta",
            "copy_summary",
            "visual_direction",
            "image_prompt",
            "panel_goal",
            "dominant_message",
            "visual_focus",
            "supporting_lines",
            "proof_points",
            "stat_highlights",
            "ordered_story_beats",
            "headline_patterns",
            "reasoning",
        )

        def add_fragment(candidate: Any) -> None:
            if len(fragments) >= limit:
                return
            preview = cls._value_preview(candidate, limit=220)
            if isinstance(preview, str):
                cleaned = cls._repair_encoding_noise(preview).strip()
                if cls._is_noise_text(cleaned):
                    return
                if cleaned not in fragments:
                    fragments.append(cleaned)
                return
            if isinstance(preview, list):
                for item in preview:
                    add_fragment(item)
                    if len(fragments) >= limit:
                        return

        def visit(candidate: Any) -> None:
            if len(fragments) >= limit or not cls._has_meaningful_value(candidate):
                return
            if isinstance(candidate, str):
                add_fragment(candidate)
                return
            if isinstance(candidate, dict):
                for key in preferred_keys:
                    if key in candidate:
                        visit(candidate.get(key))
                        if len(fragments) >= limit:
                            return
                for key, item in candidate.items():
                    if str(key) in {"from", "content_focus", "visual_role", "format", "unit_type", "stage", "trace_id"}:
                        continue
                    if cls._is_technical_key(str(key)):
                        continue
                    visit(item)
                    if len(fragments) >= limit:
                        return
                return
            if isinstance(candidate, (list, tuple, set)):
                for item in candidate:
                    visit(item)
                    if len(fragments) >= limit:
                        return
                return
            add_fragment(candidate)

        visit(value)
        return fragments[:limit]

    @classmethod
    def _dedupe_texts(cls, values: list[str], *, limit: int = 6) -> list[str]:
        seen: set[str] = set()
        cleaned_values: list[str] = []
        for value in values:
            text = cls._repair_encoding_noise(str(value or "").strip())
            if not text:
                continue
            folded = text.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            cleaned_values.append(text)
            if len(cleaned_values) >= limit:
                break
        return cleaned_values

    @classmethod
    def _list_sentence(cls, values: list[str]) -> str:
        items = cls._dedupe_texts(values, limit=4)
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return f"{', '.join(items[:-1])}, and {items[-1]}"

    @classmethod
    def _clean_reference_content(cls, value: str) -> str:
        text = cls._repair_encoding_noise(str(value or "").strip())
        if not text:
            return ""
        text = re.sub(r"#[0-9A-Fa-f]{3,8}", "", text)
        parts = re.split(r"[.;]\s*", text)
        keep: list[str] = []
        blocked_prefixes = (
            "layout ",
            "background ",
            "palette",
            "typography",
            "editable zones",
            "primary ",
            "accent ",
        )
        for part in parts:
            fragment = " ".join(part.split()).strip(" -,:")
            lowered = fragment.casefold()
            if not fragment:
                continue
            if any(lowered.startswith(prefix) for prefix in blocked_prefixes):
                continue
            if lowered in {"logo", "image", "body", "headline"}:
                continue
            if len(fragment) < 6:
                continue
            keep.append(fragment)
        if keep:
            heading = keep[0]
            lowered = heading.casefold()
            if "global context" in lowered:
                return "global context framing"
            if "next steps" in lowered or "oversight" in lowered:
                return "next steps and oversight framing"
            if "industry" in lowered and "impact" in lowered:
                return "industry impact framing"
            if "impact on" in lowered or ("impact" in lowered and ("investor" in lowered or "startup" in lowered)):
                return "impact-focused framing"
            if "takeaway" in lowered:
                return "takeaway framing"
            if len(heading.split()) <= 6:
                return f"{heading.lower()} framing"
        return ". ".join(cls._dedupe_texts(keep, limit=4))

    @classmethod
    def _extract_request_context(cls, payload: dict[str, Any]) -> dict[str, str]:
        data_used = payload.get("data_passed_for_image_generation") if isinstance(payload.get("data_passed_for_image_generation"), dict) else {}
        form_data = data_used.get("form_data_used") if isinstance(data_used.get("form_data_used"), dict) else {}
        request_content = form_data.get("requested_content") if isinstance(form_data.get("requested_content"), dict) else {}
        generation_goal = form_data.get("generation_goal") if isinstance(form_data.get("generation_goal"), dict) else {}
        brand_space_inputs = form_data.get("brand_space_form_inputs_used") if isinstance(form_data.get("brand_space_form_inputs_used"), dict) else {}
        studio_settings_used = brand_space_inputs.get("studio_settings_used") if isinstance(brand_space_inputs.get("studio_settings_used"), dict) else {}
        selected_persona_used = brand_space_inputs.get("selected_persona_used") if isinstance(brand_space_inputs.get("selected_persona_used"), dict) else {}
        selected_objective_used = brand_space_inputs.get("selected_objective_used") if isinstance(brand_space_inputs.get("selected_objective_used"), dict) else {}
        return {
            "prompt": cls._repair_encoding_noise(str(request_content.get("prompt") or "").strip()),
            "rewrite_instruction": cls._repair_encoding_noise(str(request_content.get("rewrite_instruction") or "").strip()),
            "format": str(studio_settings_used.get("format") or generation_goal.get("format") or payload.get("format") or "").strip(),
            "platform": str(studio_settings_used.get("platform_preset") or generation_goal.get("platform_preset") or "").strip(),
            "file_type": str(studio_settings_used.get("file_type") or generation_goal.get("file_type") or "").strip(),
            "persona_name": cls._repair_encoding_noise(str(selected_persona_used.get("name") or "").strip()),
            "persona_role": cls._repair_encoding_noise(str(selected_persona_used.get("role") or "").strip()),
            "objective_name": cls._repair_encoding_noise(str(selected_objective_used.get("name") or "").strip()),
            "objective_description": cls._repair_encoding_noise(str(selected_objective_used.get("description") or "").strip()),
        }

    @classmethod
    def _extract_brand_context(cls, payload: dict[str, Any]) -> dict[str, Any]:
        data_used = payload.get("data_passed_for_image_generation") if isinstance(payload.get("data_passed_for_image_generation"), dict) else {}
        brand_data = data_used.get("brand_data_used") if isinstance(data_used.get("brand_data_used"), dict) else {}
        identity = brand_data.get("identity") if isinstance(brand_data.get("identity"), dict) else {}
        personas = brand_data.get("personas") if isinstance(brand_data.get("personas"), dict) else {}

        brand_description = ""
        brand_name = ""
        industry = ""
        audience = ""
        differentiators: list[str] = []
        audience_goals: list[str] = []
        objections: list[str] = []

        for item in identity.get("content_used") or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("from") or "")
            content = item.get("content")
            if source == "brand_description" and not brand_description:
                brand_description = cls._value_preview(content, limit=220) if isinstance(cls._value_preview(content, limit=220), str) else ""
            elif source == "brand_name" and not brand_name:
                brand_name = cls._value_preview(content, limit=80) if isinstance(cls._value_preview(content, limit=80), str) else ""
            elif source == "industry_category" and not industry:
                industry = cls._value_preview(content, limit=80) if isinstance(cls._value_preview(content, limit=80), str) else ""
            elif source == "audience_type" and not audience:
                audience = cls._value_preview(content, limit=80) if isinstance(cls._value_preview(content, limit=80), str) else ""
            elif source.startswith("key_differentiators"):
                if isinstance(content, list):
                    differentiators.extend([cls._repair_encoding_noise(str(entry).strip()) for entry in content if str(entry or "").strip()])
                elif isinstance(content, str):
                    differentiators.append(cls._repair_encoding_noise(content.strip()))

        for item in personas.get("content_used") or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("from") or "")
            content = item.get("content")
            if source.endswith(".audience_goals") and isinstance(content, list):
                audience_goals.extend([cls._repair_encoding_noise(str(entry).strip()) for entry in content if str(entry or "").strip()])
            elif source.endswith(".objections") and isinstance(content, list):
                objections.extend([cls._repair_encoding_noise(str(entry).strip(" \"")) for entry in content if str(entry or "").strip()])
            elif source == "personas[0]" and isinstance(content, dict) and not audience:
                audience = cls._repair_encoding_noise(str(content.get("name") or "").strip())
                if isinstance(content.get("objections"), list):
                    objections.extend([cls._repair_encoding_noise(str(entry).strip(" \"")) for entry in content.get("objections") if str(entry or "").strip()])

        return {
            "brand_description": cls._repair_encoding_noise(brand_description),
            "brand_name": cls._repair_encoding_noise(brand_name),
            "industry": cls._repair_encoding_noise(industry),
            "audience": cls._repair_encoding_noise(audience),
            "differentiators": cls._dedupe_texts(differentiators, limit=4),
            "audience_goals": cls._dedupe_texts(audience_goals, limit=4),
            "objections": cls._dedupe_texts(objections, limit=3),
        }

    @classmethod
    def _extract_sample_influence(cls, payload: dict[str, Any]) -> list[str]:
        data_used = payload.get("data_passed_for_image_generation") if isinstance(payload.get("data_passed_for_image_generation"), dict) else {}
        sample_data = data_used.get("template_or_sample_data_used") if isinstance(data_used.get("template_or_sample_data_used"), dict) else {}
        influences: list[str] = []
        for block_name in ("sample_content_adapted", "reference_content_adapted", "layout_content_adapted"):
            block = sample_data.get(block_name)
            if not isinstance(block, dict):
                continue
            fragments = cls._collect_client_text_fragments(block, limit=8)
            for fragment in fragments:
                cleaned = cls._clean_reference_content(fragment)
                if cleaned:
                    influences.append(cleaned)
        return cls._dedupe_texts(influences, limit=4)

    @classmethod
    def _sentence_block(cls, sentences: list[str]) -> str:
        cleaned: list[str] = []
        for sentence in sentences:
            text = cls._repair_encoding_noise(str(sentence or "").strip())
            if not text:
                continue
            if text[-1] not in ".!?":
                text = f"{text}."
            cleaned.append(text)
        return "\n\n".join(cleaned)

    @classmethod
    def _append_key_value(cls, lines: list[str], label: str, value: Any) -> None:
        text = cls._repair_encoding_noise(str(value or "").strip())
        if text:
            lines.append(f"- {label}: {text}")

    @classmethod
    def _append_list_values(cls, lines: list[str], label: str, values: list[str], *, item_label: str | None = None) -> None:
        cleaned = cls._dedupe_texts(values, limit=8)
        if not cleaned:
            return
        if len(cleaned) == 1 and item_label is None:
            lines.append(f"- {label}: {cleaned[0]}")
            return
        lines.append(f"- {label}:")
        prefix = item_label or "Item"
        for index, value in enumerate(cleaned, start=1):
            lines.append(f"  - {prefix} {index}: {value}")

    @classmethod
    def _start_section(cls, lines: list[str], title: str) -> None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"{title}:")

    @classmethod
    def _friendly_field_label(cls, field_name: str) -> str:
        text = str(field_name or "").strip()
        if not text:
            return "Content"
        leaf = text.split(".")[-1]
        leaf = re.sub(r"\[\d+\]$", "", leaf).strip()
        label_map = {
            "audience_type": "Audience Type",
            "brand_description": "Brand Description",
            "brand_name": "Brand Name",
            "industry_category": "Industry Category",
            "key_differentiators": "Key Differentiators",
            "audience_goals": "Audience Goals",
            "fears_and_pain_points": "Fears And Pain Points",
            "language_preference": "Language Preference",
            "content_behavior": "Content Behavior",
            "blocked_words": "Blocked Words",
            "custom_rules": "Custom Rules",
            "forbidden_prompt_patterns": "Forbidden Prompt Patterns",
            "brand_advantage": "Brand Advantage",
            "brand_mission": "Brand Mission",
            "brand_promise": "Brand Promise",
            "brand_vision": "Brand Vision",
            "business_problem_or_opportunity": "Business Problem Or Opportunity",
            "legal_disclaimers": "Legal Disclaimer",
            "applies_to_formats": "Applies To Formats",
            "background_style": "Background Style",
            "brand_color_palette": "Brand Color Palette",
            "brand_mood": "Brand Mood",
            "component_motifs": "Component Motifs",
            "platform_rules": "Platform Rules",
            "prompt_starters": "Prompt Starters",
            "market_positioning": "Market Positioning",
            "platform_scope": "Platform Scope",
            "content_type": "Content Type",
            "desired_outcomes": "Desired Outcomes",
            "comparison_points": "Comparison Points",
            "highest": "Highest Priority",
            "supplemental": "Supplemental Priority",
            "primary": "Primary Color",
            "secondary": "Secondary Color",
            "tertiary": "Tertiary Color",
            "background": "Background Color",
            "primary_hex": "Primary Color",
            "secondary_hex": "Secondary Color",
            "tertiary_hex": "Tertiary Color",
            "accent_hex": "Accent Color",
            "dominant_mode": "Dominant Mode",
        }
        return label_map.get(leaf, leaf.replace("_", " ").strip().title() or "Content")

    @classmethod
    def _preview_text_for_client(cls, value: Any, *, limit: int = 180) -> str:
        preview = cls._value_preview(value, limit=limit)
        if isinstance(preview, list):
            return cls._list_sentence([
                cls._repair_encoding_noise(str(entry).strip())
                for entry in preview
                if str(entry or "").strip() and not cls._is_noise_text(str(entry))
            ])
        if isinstance(preview, dict):
            fragments = cls._collect_client_text_fragments(preview, limit=4)
            return cls._list_sentence(fragments)
        text = cls._repair_encoding_noise(str(preview or "").strip())
        return text if not cls._is_noise_text(text) else ""

    @classmethod
    def _should_skip_brand_data_point(cls, section_name: str, field_path: str, label: str, value_text: str) -> bool:
        lowered_path = str(field_path or "").strip().lower()
        lowered_label = str(label or "").strip().lower()
        lowered_value = str(value_text or "").strip().lower()
        if not lowered_value:
            return True
        if cls._path_is_technical(lowered_path):
            return True
        if lowered_label == "content":
            return True
        if lowered_path in {str(section_name or "").strip().lower(), ""}:
            return True
        if any(token in lowered_path for token in ("url", "token", "storage", "path", "asset_id", "asset_ids")):
            return True
        if any(token in lowered_value for token in ("http://", "https://", "localhost", "/api/", "token=")):
            return True
        if re.search(r"\.(png|jpg|jpeg|pdf|webp)\b", lowered_value):
            return True
        if lowered_label in {"field", "value", "confidence", "ranking score", "is default", "field key", "channel"}:
            return True
        if "--- image ocr text ---" in lowered_value:
            return True
        if any(token in lowered_path for token in ("template_files", "recommended_templates", "other_documents")):
            if lowered_label in {"name", "kind", "lifecycle state"}:
                return True
        if "logo_assets" in lowered_path:
            return True
        return False

    @classmethod
    def _extract_brand_data_points(
        cls,
        *,
        section_name: str,
        field_name: str,
        content: Any,
        limit: int = 6,
    ) -> list[dict[str, str]]:
        data_points: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add_point(path: str, candidate: Any) -> None:
            if len(data_points) >= limit:
                return
            label = cls._friendly_field_label(path or field_name)
            value_text = cls._preview_text_for_client(candidate, limit=180)
            if cls._should_skip_brand_data_point(section_name, path or field_name, label, value_text):
                return
            dedupe_key = (label.casefold(), value_text.casefold())
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            if "template_files" in str(path or field_name):
                if label == "Tags":
                    label = "Reference Categories"
                elif label == "Template Files":
                    label = "Reference Content"
            data_points.append({"label": label, "value": value_text, "source_field": path or field_name})

        if isinstance(content, (str, int, float, bool)):
            add_point(field_name, content)
            return data_points

        if isinstance(content, (dict, list, tuple, set)):
            records = cls._collect_field_previews(content, prefix=field_name, limit=limit * 2)
            for record in records:
                if not isinstance(record, dict):
                    continue
                path = str(record.get("field") or "").strip()
                value_preview = record.get("value_preview")
                if path.endswith("]") and "." not in path and "[" in path:
                    continue
                add_point(path, value_preview)
                if len(data_points) >= limit:
                    break

        if not data_points:
            add_point(field_name, content)
        return data_points

    @classmethod
    def _brand_section_usage(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data_used = payload.get("data_passed_for_image_generation") if isinstance(payload.get("data_passed_for_image_generation"), dict) else {}
        brand_data = data_used.get("brand_data_used") if isinstance(data_used.get("brand_data_used"), dict) else {}
        usage: list[dict[str, Any]] = []
        for section_name, section_payload in brand_data.items():
            if not isinstance(section_payload, dict):
                continue
            if not cls._has_meaningful_value(section_payload.get("content_used")) and not cls._has_meaningful_value(section_payload.get("section_summary")):
                continue
            focus = [
                str(item).strip()
                for item in (section_payload.get("content_focus") or [])
                if str(item).strip() and str(item).strip() != str(section_name).strip()
            ][:8]
            data_points: list[dict[str, str]] = []
            for item in (section_payload.get("content_used") or []):
                if not isinstance(item, dict):
                    continue
                field_name = str(item.get("from") or "").strip()
                content = item.get("content")
                if re.search(r"\[\d+\]$", field_name) and not isinstance(content, (dict, list, tuple, set)):
                    continue
                extracted_points = cls._extract_brand_data_points(
                    section_name=str(section_name).strip(),
                    field_name=field_name,
                    content=content,
                    limit=6,
                )
                for point in extracted_points:
                    if point not in data_points:
                        data_points.append(point)
                if len(data_points) >= 6:
                    break
            usage.append(
                {
                    "section_name": str(section_name).strip(),
                    "friendly_name": str(section_name).replace("_", " ").strip().title(),
                    "focus": focus,
                    "data_points": data_points,
                }
            )
        return usage

    @classmethod
    def _append_brand_section_usage_lines(
        cls,
        lines: list[str],
        section_usage: list[dict[str, Any]],
        *,
        heading: str,
    ) -> None:
        lines.append(heading)
        if not section_usage:
            lines.append("  - No used brand-space sections were identified in the trace JSON.")
            return
        for index, item in enumerate(section_usage, start=1):
            label = item.get("friendly_name") or item.get("section_name") or f"Section {index}"
            focus = item.get("focus") if isinstance(item.get("focus"), list) else []
            data_points = item.get("data_points") if isinstance(item.get("data_points"), list) else []
            if focus:
                lines.append(f"  - Section {index}: {label} - {', '.join(focus)}")
            else:
                lines.append(f"  - Section {index}: {label}")
            if data_points:
                for point in data_points:
                    if not isinstance(point, dict):
                        continue
                    point_label = cls._repair_encoding_noise(str(point.get("label") or "").strip())
                    point_value = cls._repair_encoding_noise(str(point.get("value") or "").strip())
                    if point_value:
                        lines.append(f"    - {point_label}: {point_value}")

    @classmethod
    def _append_brand_space_sections_used(cls, lines: list[str], payload: dict[str, Any]) -> None:
        cls._append_brand_section_usage_lines(
            lines,
            cls._brand_section_usage(payload),
            heading="- Brand space sections used:",
        )

    @classmethod
    def _stage_brand_section_allowlist(cls, stage_name: str) -> dict[str, list[str]]:
        stage = str(stage_name or "").strip().lower()
        shared_identity = ["audience_type", "brand_description", "brand_name", "industry_category", "key_differentiators"]
        shared_persona = ["name", "role", "objections", "audience_goals"]
        shared_objective = ["name", "description", "content_type", "market_positioning", "platform_scope"]
        shared_voice = ["primary_emotion", "secondary_emotion", "perspective", "content_complexity", "avoided_emotion"]
        if stage == "planning_strategy":
            return {
                "identity": shared_identity,
                "personas": shared_persona,
                "objectives": shared_objective,
                "guardrails": ["blocked_words", "custom_rules", "dos", "donts"],
                "voice_tone": shared_voice,
                "foundations": ["brand_mission", "brand_promise", "brand_vision", "business_problem_or_opportunity"],
                "audience_insights": ["desired_outcomes", "motivations", "comparison_points"],
            }
        if stage == "content_generation":
            return {
                "identity": shared_identity,
                "personas": shared_persona,
                "guardrails": ["blocked_words", "custom_rules", "dos", "donts"],
                "voice_tone": shared_voice,
                "objectives": shared_objective,
                "foundations": ["brand_promise", "brand_mission", "brand_advantage"],
                "brand_assets": ["legal_disclaimers", "applies_to_formats"],
            }
        if stage == "layout_planning":
            return {
                "identity": ["brand_name", "audience_type"],
                "visual_identity": ["background_style", "brand_mood", "dominant_mode", "primary_hex", "secondary_hex", "tertiary_hex", "accent_hex", "brand_color_palette"],
                "brand_assets": ["legal_disclaimers", "applies_to_formats"],
                "guardrails": ["blocked_words", "custom_rules"],
                "objectives": ["market_positioning", "content_type", "platform_scope"],
                "prompt_intelligence": ["platform_rules"],
            }
        if stage == "visual_planning":
            return {
                "identity": ["brand_name", "audience_type", "brand_description"],
                "visual_identity": ["background_style", "brand_mood", "dominant_mode", "primary_hex", "secondary_hex", "tertiary_hex", "accent_hex", "brand_color_palette", "component_motifs"],
                "brand_assets": ["legal_disclaimers", "applies_to_formats"],
                "voice_tone": ["primary_emotion", "secondary_emotion", "perspective"],
                "guardrails": ["blocked_words", "custom_rules"],
            }
        if stage == "slide_trace":
            return {
                "identity": shared_identity,
                "personas": shared_persona,
                "objectives": shared_objective,
                "guardrails": ["blocked_words", "custom_rules"],
                "voice_tone": shared_voice,
                "foundations": ["brand_promise", "brand_mission", "brand_advantage"],
                "brand_assets": ["legal_disclaimers", "applies_to_formats"],
                "visual_identity": ["background_style", "brand_mood", "dominant_mode", "primary_hex", "secondary_hex", "tertiary_hex", "accent_hex", "brand_color_palette"],
            }
        return {}

    @classmethod
    def _field_matches_allowlist(cls, field_path: str, allowed_fields: list[str]) -> bool:
        path = str(field_path or "").strip().lower()
        if not path:
            return False
        for field in allowed_fields:
            candidate = str(field or "").strip().lower()
            if not candidate:
                continue
            if (
                path == candidate
                or path.endswith(f".{candidate}")
                or path.startswith(f"{candidate}[")
                or path.startswith(f"{candidate}.")
                or f".{candidate}[" in path
            ):
                return True
        return False

    @classmethod
    def _brand_stage_section_map(cls, payload: dict[str, Any], stage_name: str) -> dict[str, list[dict[str, str]]]:
        section_map: dict[str, list[dict[str, str]]] = {}
        for item in cls._brand_section_usage_for_stage(payload, stage_name):
            if not isinstance(item, dict):
                continue
            section_name = str(item.get("section_name") or "").strip().lower()
            points = [point for point in (item.get("data_points") or []) if isinstance(point, dict)]
            if section_name and points:
                section_map[section_name] = points
        return section_map

    @classmethod
    def _section_values_by_label(
        cls,
        section_map: dict[str, list[dict[str, str]]],
        section_name: str,
        labels: list[str],
    ) -> list[str]:
        points = section_map.get(str(section_name or "").strip().lower(), [])
        allowed = {str(label or "").strip().casefold() for label in labels if str(label or "").strip()}
        values: list[str] = []
        for point in points:
            label = str(point.get("label") or "").strip().casefold()
            value = cls._repair_encoding_noise(str(point.get("value") or "").strip())
            if label in allowed and value:
                values.append(value)
        return cls._dedupe_texts(values, limit=6)

    @classmethod
    def _palette_usage_summary(cls, payload: dict[str, Any], stage_name: str) -> dict[str, Any]:
        section_map = cls._brand_stage_section_map(payload, stage_name)
        colors: dict[str, Any] = {}
        visual_points = section_map.get("visual_identity", [])
        label_to_key = {
            "primary color": "primary",
            "secondary color": "secondary",
            "tertiary color": "tertiary",
            "accent color": "accent",
            "background color": "background",
        }
        for point in visual_points:
            label = str(point.get("label") or "").strip().casefold()
            value = cls._repair_encoding_noise(str(point.get("value") or "").strip())
            if label in label_to_key and value:
                colors[label_to_key[label]] = value

        layout_output = payload.get("layout_planning_output") if isinstance(payload.get("layout_planning_output"), dict) else {}
        blueprint = layout_output.get("blueprint_used") if isinstance(layout_output.get("blueprint_used"), dict) else {}
        brand_rules = blueprint.get("brand_rules_applied") if isinstance(blueprint.get("brand_rules_applied"), dict) else {}
        palette_roles = brand_rules.get("palette_roles") if isinstance(brand_rules.get("palette_roles"), dict) else {}
        for key in ("primary", "secondary", "tertiary", "accent", "background"):
            if not colors.get(key) and str(palette_roles.get(key) or "").strip():
                colors[key] = str(palette_roles.get(key) or "").strip()
        additional = []
        for item in (palette_roles.get("additional") or [])[:4] if isinstance(palette_roles, dict) else []:
            if not isinstance(item, dict):
                continue
            hex_code = str(item.get("hex") or "").strip()
            name = str(item.get("name") or "").strip()
            if hex_code:
                additional.append(f"{name}: {hex_code}" if name else hex_code)
        return {
            "primary": colors.get("primary"),
            "secondary": colors.get("secondary"),
            "tertiary": colors.get("tertiary"),
            "accent": colors.get("accent"),
            "background": colors.get("background"),
            "additional": cls._dedupe_texts(additional, limit=4),
        }

    @classmethod
    def _intelligence_evidence(cls, stage_name: str, payload: dict[str, Any]) -> dict[str, list[str]]:
        request = cls._extract_request_context(payload)
        brand = cls._extract_brand_context(payload)
        stage = str(stage_name or "").strip().lower()
        section_map = cls._brand_stage_section_map(payload, stage_name)
        strategy = payload.get("strategy_output") if isinstance(payload.get("strategy_output"), dict) else {}
        content_output = payload.get("content_generation_output") if isinstance(payload.get("content_generation_output"), dict) else {}
        layout_output = payload.get("layout_planning_output") if isinstance(payload.get("layout_planning_output"), dict) else {}
        visual_output = payload.get("visual_content_used_for_image_generation") if isinstance(payload.get("visual_content_used_for_image_generation"), dict) else {}
        slide_output = payload.get("slide_or_section_trace") if isinstance(payload.get("slide_or_section_trace"), dict) else {}

        if stage == "planning_strategy":
            return {
                "strategic_reasoning": cls._dedupe_texts([
                    str(strategy.get("angle") or "").strip(),
                    str(strategy.get("thesis") or "").strip(),
                    str(strategy.get("reader_payoff") or "").strip(),
                    str(strategy.get("hook_strategy") or "").strip(),
                ], limit=4),
                "audience_intelligence": cls._dedupe_texts([
                    *cls._section_values_by_label(section_map, "personas", ["Audience Goals", "Objections"]),
                    *cls._section_values_by_label(section_map, "audience_insights", ["Desired Outcomes", "Comparison Points"]),
                ], limit=4),
                "campaign_intelligence": cls._dedupe_texts([
                    f"Format family: {strategy.get('format_family')}" if str(strategy.get("format_family") or "").strip() else "",
                    f"Preferred slide count: {strategy.get('preferred_slide_count')}" if strategy.get("preferred_slide_count") else "",
                    *[f"Outline role: {str(item.get('role') or '').strip()}" for item in (strategy.get("outline") or [])[:5] if isinstance(item, dict) and str(item.get("role") or "").strip()],
                ], limit=6),
                "brand_conditioning": cls._dedupe_texts([
                    brand.get("brand_description") or "",
                    *cls._section_values_by_label(section_map, "guardrails", ["Blocked Words", "Custom Rules"]),
                    *cls._section_values_by_label(section_map, "voice_tone", ["Primary Emotion", "Perspective"]),
                    *cls._section_values_by_label(section_map, "foundations", ["Brand Promise", "Brand Mission"]),
                ], limit=5),
                "prioritization_logic": cls._dedupe_texts([
                    *cls._section_values_by_label(section_map, "context_priority", ["Highest Priority", "Supplemental Priority"]),
                    str(strategy.get("research_guard") or "").strip(),
                ], limit=4),
            }

        if stage == "content_generation":
            message_strategy = content_output.get("message_strategy_used") if isinstance(content_output.get("message_strategy_used"), dict) else {}
            generated = content_output.get("generated_content_for_image") if isinstance(content_output.get("generated_content_for_image"), dict) else {}
            content_plan = content_output.get("content_plan_used") if isinstance(content_output.get("content_plan_used"), dict) else {}
            return {
                "strategic_reasoning": cls._dedupe_texts([
                    str(message_strategy.get("headline_direction") or "").strip(),
                    str(message_strategy.get("core_audience_message") or "").strip(),
                    str(message_strategy.get("cta_intent") or "").strip(),
                ], limit=4),
                "audience_intelligence": cls._dedupe_texts([
                    *cls._section_values_by_label(section_map, "personas", ["Audience Goals", "Objections"]),
                    f"Audience: {brand.get('audience')}" if brand.get("audience") else "",
                ], limit=4),
                "campaign_intelligence": cls._dedupe_texts([
                    f"Sequence contract: {content_plan.get('sequence_contract')}" if str(content_plan.get("sequence_contract") or "").strip() else "",
                    f"Carousel archetype: {content_plan.get('carousel_archetype')}" if str(content_plan.get("carousel_archetype") or "").strip() else "",
                    *[str(item).strip() for item in (content_plan.get("planning_rules") or []) if str(item).strip()],
                ], limit=6),
                "brand_conditioning": cls._dedupe_texts([
                    *cls._section_values_by_label(section_map, "guardrails", ["Blocked Words", "Custom Rules"]),
                    *cls._section_values_by_label(section_map, "voice_tone", ["Primary Emotion", "Perspective"]),
                    *cls._section_values_by_label(section_map, "foundations", ["Brand Promise", "Brand Mission", "Brand Advantage"]),
                ], limit=5),
                "advertising_behavior": cls._dedupe_texts([
                    str(generated.get("headline") or "").strip(),
                    str(generated.get("body") or "").strip(),
                    str(generated.get("cta") or "").strip(),
                    *[str(item).strip() for item in (message_strategy.get("important_keywords") or []) if str(item).strip()],
                ], limit=6),
            }

        if stage == "layout_planning":
            decision = layout_output.get("layout_decision_used") if isinstance(layout_output.get("layout_decision_used"), dict) else {}
            blueprint = layout_output.get("blueprint_used") if isinstance(layout_output.get("blueprint_used"), dict) else {}
            palette = cls._palette_usage_summary(payload, stage_name)
            return {
                "visual_intelligence": cls._dedupe_texts([
                    *[str(item).strip() for item in (decision.get("reasoning") or []) if str(item).strip()],
                    f"Layout type: {blueprint.get('layout_type')}" if str(blueprint.get("layout_type") or "").strip() else "",
                    f"Layout mode: {decision.get('mode')}" if str(decision.get("mode") or "").strip() else "",
                    *[f"Zone: {str(item).strip()}" for item in (blueprint.get("zone_roles") or []) if str(item).strip()],
                ], limit=8),
                "campaign_intelligence": cls._dedupe_texts([
                    f"Format: {request.get('format')}" if request.get("format") else "",
                    f"Platform: {request.get('platform')}" if request.get("platform") else "",
                    f"Sequence support: {blueprint.get('source_mode')}" if str(blueprint.get("source_mode") or "").strip() else "",
                ], limit=4),
                "brand_conditioning": cls._dedupe_texts([
                    *cls._section_values_by_label(section_map, "brand_assets", ["Legal Disclaimer", "Applies To Formats"]),
                    *cls._section_values_by_label(section_map, "guardrails", ["Blocked Words", "Custom Rules"]),
                ], limit=4),
                "prioritization_logic": cls._dedupe_texts([
                    str(decision.get("asset_strategy") or "").strip(),
                    str(decision.get("adaptations") or "").strip(),
                    *[str(item).strip() for item in (decision.get("review_flags") or []) if str(item).strip()],
                ], limit=5),
                "color_system": cls._dedupe_texts([
                    f"Primary color: {palette.get('primary')}" if palette.get("primary") else "",
                    f"Secondary color: {palette.get('secondary')}" if palette.get("secondary") else "",
                    f"Tertiary color: {palette.get('tertiary')}" if palette.get("tertiary") else "",
                    f"Accent color: {palette.get('accent')}" if palette.get("accent") else "",
                    f"Background color: {palette.get('background')}" if palette.get("background") else "",
                    *[f"Additional palette: {item}" for item in (palette.get("additional") or [])],
                ], limit=8),
            }

        if stage == "visual_planning":
            visual_content = visual_output.get("visual_content_used") if isinstance(visual_output.get("visual_content_used"), dict) else {}
            visual_plan = visual_output.get("visual_plan_used") if isinstance(visual_output.get("visual_plan_used"), dict) else {}
            palette = cls._palette_usage_summary(payload, stage_name)
            chart_signals = visual_content.get("graph_or_chart_content_used") if isinstance(visual_content.get("graph_or_chart_content_used"), list) else []
            visual_elements = visual_content.get("visual_elements_used") if isinstance(visual_content.get("visual_elements_used"), list) else []
            return {
                "visual_intelligence": cls._dedupe_texts([
                    str(visual_content.get("visual_direction") or "").strip(),
                    str(visual_content.get("design_style") or "").strip(),
                    str(visual_content.get("image_prompt") or "").strip(),
                    f"Execution mode: {visual_plan.get('execution_mode')}" if str(visual_plan.get("execution_mode") or "").strip() else "",
                    *[str(item.get("text") or item.get("visual_idea") or "").strip() for item in visual_elements[:4] if isinstance(item, dict)],
                    *[str(item.get("scene_graph_role") or item.get("section_role") or "").strip() for item in chart_signals[:4] if isinstance(item, dict)],
                ], limit=8),
                "audience_intelligence": cls._dedupe_texts([
                    f"Audience: {brand.get('audience')}" if brand.get("audience") else "",
                    *cls._section_values_by_label(section_map, "voice_tone", ["Primary Emotion", "Secondary Emotion", "Perspective"]),
                ], limit=4),
                "brand_conditioning": cls._dedupe_texts([
                    *cls._section_values_by_label(section_map, "guardrails", ["Blocked Words", "Custom Rules"]),
                    *cls._section_values_by_label(section_map, "brand_assets", ["Legal Disclaimer", "Applies To Formats"]),
                ], limit=4),
                "color_system": cls._dedupe_texts([
                    f"Primary color: {palette.get('primary')}" if palette.get("primary") else "",
                    f"Secondary color: {palette.get('secondary')}" if palette.get("secondary") else "",
                    f"Tertiary color: {palette.get('tertiary')}" if palette.get("tertiary") else "",
                    f"Accent color: {palette.get('accent')}" if palette.get("accent") else "",
                    f"Background color: {palette.get('background')}" if palette.get("background") else "",
                    *[f"Additional palette: {item}" for item in (palette.get("additional") or [])],
                ], limit=8),
            }

        if stage == "slide_trace":
            units = slide_output.get("units") if isinstance(slide_output.get("units"), list) else []
            source = slide_output.get("source_samples_adapted") if isinstance(slide_output.get("source_samples_adapted"), dict) else {}
            return {
                "campaign_intelligence": cls._dedupe_texts([
                    f"Carousel archetype: {source.get('carousel_archetype')}" if str(source.get("carousel_archetype") or "").strip() else "",
                    f"Narrative contract: {source.get('narrative_contract')}" if str(source.get("narrative_contract") or "").strip() else "",
                    *[str(item).strip() for item in (source.get("ordered_story_beats") or []) if str(item).strip()],
                ], limit=8),
                "strategic_reasoning": cls._dedupe_texts([
                    *[f"Slide role: {str(item.get('slide_role') or item.get('section_role') or '').strip()}" for item in units[:8] if isinstance(item, dict) and str(item.get("slide_role") or item.get("section_role") or "").strip()],
                    *[str(item.get("transition_note") or "").strip() for item in units[:8] if isinstance(item, dict) and str(item.get("transition_note") or "").strip()],
                ], limit=8),
                "brand_conditioning": cls._dedupe_texts([
                    *cls._section_values_by_label(section_map, "guardrails", ["Blocked Words", "Custom Rules"]),
                    *cls._section_values_by_label(section_map, "foundations", ["Brand Promise", "Brand Mission", "Brand Advantage"]),
                    *cls._section_values_by_label(section_map, "brand_assets", ["Legal Disclaimer", "Applies To Formats"]),
                ], limit=5),
                "audience_intelligence": cls._dedupe_texts([
                    *cls._section_values_by_label(section_map, "personas", ["Audience Goals", "Objections"]),
                    f"Audience: {brand.get('audience')}" if brand.get("audience") else "",
                ], limit=4),
            }

        return {}

    @classmethod
    def _append_intelligence_evidence(cls, lines: list[str], payload: dict[str, Any], stage_name: str) -> None:
        evidence = cls._intelligence_evidence(stage_name, payload)
        section_titles = {
            "strategic_reasoning": "Strategic Reasoning Used",
            "audience_intelligence": "Audience Intelligence Used",
            "campaign_intelligence": "Campaign Intelligence Used",
            "brand_conditioning": "Brand Conditioning Used",
            "prioritization_logic": "Prioritization Logic Used",
            "visual_intelligence": "Visual Intelligence Used",
            "advertising_behavior": "Advertising Behavior Used",
            "color_system": "Color System Used",
        }
        for key in (
            "strategic_reasoning",
            "audience_intelligence",
            "campaign_intelligence",
            "brand_conditioning",
            "prioritization_logic",
            "visual_intelligence",
            "advertising_behavior",
            "color_system",
        ):
            values = evidence.get(key) if isinstance(evidence.get(key), list) else []
            if not values:
                continue
            section_start = len(lines)
            cls._start_section(lines, section_titles[key])
            cls._append_list_values(lines, "Signals", values, item_label="Signal")
            cls._ensure_section_content(lines, section_start)

    @classmethod
    def _brand_section_usage_for_stage(cls, payload: dict[str, Any], stage_name: str) -> list[dict[str, Any]]:
        allowlist = cls._stage_brand_section_allowlist(stage_name)
        section_usage = cls._brand_section_usage(payload)
        if not allowlist:
            return section_usage
        filtered_usage: list[dict[str, Any]] = []
        for item in section_usage:
            if not isinstance(item, dict):
                continue
            section_name = str(item.get("section_name") or "").strip().lower()
            allowed_fields = allowlist.get(section_name)
            if not allowed_fields:
                continue
            filtered_points: list[dict[str, str]] = []
            for point in (item.get("data_points") or []):
                if not isinstance(point, dict):
                    continue
                source_field = str(point.get("source_field") or "").strip()
                if not cls._field_matches_allowlist(source_field, allowed_fields):
                    continue
                filtered_points.append(point)
            if not filtered_points:
                continue
            filtered_usage.append(
                {
                    "section_name": item.get("section_name"),
                    "friendly_name": item.get("friendly_name"),
                    "focus": [field for field in (item.get("focus") or []) if field in allowed_fields][:8],
                    "data_points": filtered_points,
                }
            )
        return filtered_usage

    @classmethod
    def _ensure_section_content(cls, lines: list[str], section_start_index: int, *, empty_message: str = "None identified from the trace JSON.") -> None:
        if len(lines) == section_start_index + 1:
            lines.append(f"- {empty_message}")

    @classmethod
    def _brand_following_score(cls, payload: dict[str, Any]) -> dict[str, Any]:
        brand = cls._extract_brand_context(payload)
        compliance = payload.get("brand_evaluation_and_compliance") if isinstance(payload.get("brand_evaluation_and_compliance"), dict) else {}
        scene = compliance.get("scene_graph_validation") if isinstance(compliance.get("scene_graph_validation"), dict) else {}
        semantic = compliance.get("content_semantic_validation") if isinstance(compliance.get("content_semantic_validation"), dict) else {}
        guardrails = compliance.get("guardrails_applied")

        coverage_score = 0
        reasons: list[str] = []

        if brand.get("brand_name"):
            coverage_score += 15
            reasons.append("Brand name is present in the generation trace.")
        if brand.get("audience"):
            coverage_score += 15
            reasons.append("Audience information is present in the generation trace.")
        if brand.get("brand_description") or brand.get("industry"):
            coverage_score += 10
            reasons.append("Brand context is present in the generation trace.")
        if brand.get("differentiators"):
            coverage_score += 20
            reasons.append("Key differentiators are present in the generation trace.")
        if brand.get("audience_goals"):
            coverage_score += 10
            reasons.append("Audience goals are present in the generation trace.")
        section_usage = cls._brand_section_usage(payload)
        if section_usage:
            coverage_score += min(len(section_usage), 10)
            reasons.append(f"{len(section_usage)} brand-space sections were used in this stage.")
        if guardrails:
            coverage_score += 10
            reasons.append("Brand guardrails were applied during generation.")

        score = coverage_score

        scene_status = str(scene.get("status") or "").strip().lower()
        scene_issue_count = int(scene.get("issue_count") or 0)
        if scene_status in {"ok", "pass", "passed", "clean"}:
            score += 10
            reasons.append("Scene graph validation did not report major brand-following issues.")
        elif scene_issue_count:
            penalty = min(scene_issue_count * 6, 24)
            score -= penalty
            reasons.append(f"Scene graph validation reported {scene_issue_count} warning(s), which reduced the score.")

        semantic_status = str(semantic.get("status") or "").strip().lower()
        semantic_issues = semantic.get("issues") if isinstance(semantic.get("issues"), list) else []
        if semantic_status in {"ok", "pass", "passed", "clean"}:
            score += 10
            reasons.append("Content semantic validation stayed aligned with the intended content.")
        elif semantic_issues:
            penalty = min(len(semantic_issues) * 5, 20)
            score -= penalty
            reasons.append(f"Content semantic validation reported {len(semantic_issues)} issue(s), which reduced the score.")

        score = max(0, min(100, score))
        if score >= 85:
            level = "High"
        elif score >= 65:
            level = "Medium"
        else:
            level = "Low"
        return {
            "score": score,
            "level": level,
            "reasons": cls._dedupe_texts(reasons, limit=6),
        }

    @classmethod
    def _append_brand_following_score(cls, lines: list[str], payload: dict[str, Any]) -> None:
        score_summary = cls._brand_following_score(payload)
        cls._start_section(lines, "Brand Following Score")
        cls._append_key_value(lines, "Score", f"{score_summary['score']}/100")
        cls._append_key_value(lines, "Level", score_summary["level"])
        cls._append_list_values(lines, "Why this score was given", score_summary["reasons"], item_label="Reason")
        cls._ensure_section_content(lines, len(lines) - 3)

    @classmethod
    def _humanize_goal(cls, request: dict[str, str]) -> str:
        parts: list[str] = []
        if request.get("format"):
            parts.append(request["format"])
        if request.get("platform"):
            parts.append(request["platform"])
        if not parts:
            return "image"
        return " ".join(parts) + " image"

    @classmethod
    def _planning_stage_summary(cls, payload: dict[str, Any]) -> str:
        request = cls._extract_request_context(payload)
        brand = cls._extract_brand_context(payload)
        sample_influence = cls._extract_sample_influence(payload)
        strategy = payload.get("strategy_output") if isinstance(payload.get("strategy_output"), dict) else {}
        topic = cls._repair_encoding_noise(str(strategy.get("topic_focus") or request.get("prompt") or "").strip())
        angle = cls._repair_encoding_noise(str(strategy.get("angle") or "").strip())
        hook = cls._repair_encoding_noise(str(strategy.get("hook_strategy") or "").strip())
        payoff = cls._repair_encoding_noise(str(strategy.get("reader_payoff") or "").strip())

        lines = ["Planning Strategy"]
        section_start = len(lines)
        cls._start_section(lines, "Brand Data Used")
        cls._append_key_value(lines, "Brand name", brand.get("brand_name"))
        cls._append_key_value(lines, "Audience", brand.get("audience"))
        cls._append_key_value(lines, "Industry", brand.get("industry"))
        cls._append_key_value(lines, "Brand description", brand.get("brand_description"))
        cls._append_list_values(lines, "Key differentiators", brand.get("differentiators") or [], item_label="Point")
        cls._append_list_values(lines, "Audience goals", brand.get("audience_goals") or [], item_label="Goal")
        cls._append_brand_section_usage_lines(
            lines,
            cls._brand_section_usage_for_stage(payload, "planning_strategy"),
            heading="- Brand space sections used in planning:",
        )
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Form Data Used")
        cls._append_key_value(lines, "Selected persona", request.get("persona_name"))
        cls._append_key_value(lines, "Persona role", request.get("persona_role"))
        cls._append_key_value(lines, "Selected objective", request.get("objective_name"))
        cls._append_key_value(lines, "Objective description", request.get("objective_description"))
        cls._append_key_value(lines, "Selected format", request.get("format"))
        cls._append_key_value(lines, "Selected platform", request.get("platform"))
        cls._append_key_value(lines, "Selected file type", request.get("file_type"))
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Template or Sample Data Used")
        cls._append_list_values(lines, "Content patterns adapted", sample_influence, item_label="Pattern")
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Planning Content Used")
        cls._append_key_value(lines, "Topic focus", topic)
        cls._append_key_value(lines, "Planning angle", angle)
        cls._append_key_value(lines, "Reader takeaway", payoff)
        if hook:
            lowered_hook = hook[0].lower() + hook[1:] if len(hook) > 1 else hook.lower()
            lowered_hook = re.sub(r"^open with\s+", "", lowered_hook, flags=re.IGNORECASE)
            cls._append_key_value(lines, "Opening emphasis", lowered_hook)
        cls._ensure_section_content(lines, section_start)
        cls._append_intelligence_evidence(lines, payload, "planning_strategy")
        cls._append_brand_following_score(lines, payload)
        return "\n".join(lines)

    @classmethod
    def _content_stage_summary(cls, payload: dict[str, Any]) -> str:
        request = cls._extract_request_context(payload)
        brand = cls._extract_brand_context(payload)
        sample_influence = cls._extract_sample_influence(payload)
        output = payload.get("content_generation_output") if isinstance(payload.get("content_generation_output"), dict) else {}
        content_plan = output.get("content_plan_used") if isinstance(output.get("content_plan_used"), dict) else {}
        message_strategy = output.get("message_strategy_used") if isinstance(output.get("message_strategy_used"), dict) else {}
        generated = output.get("generated_content_for_image") if isinstance(output.get("generated_content_for_image"), dict) else {}

        headline = cls._repair_encoding_noise(str(generated.get("headline") or message_strategy.get("headline_direction") or "").strip())
        body = cls._repair_encoding_noise(str(generated.get("body") or "").strip())
        cta = cls._repair_encoding_noise(str(generated.get("cta") or message_strategy.get("cta_intent") or "").strip())
        keywords = cls._dedupe_texts([str(item).strip() for item in (message_strategy.get("important_keywords") or []) if str(item or "").strip()], limit=4)
        rules = cls._dedupe_texts([str(item).strip() for item in (content_plan.get("planning_rules") or []) if str(item or "").strip()], limit=3)

        lines = ["Content Generation"]
        section_start = len(lines)
        cls._start_section(lines, "Brand Data Used")
        cls._append_key_value(lines, "Brand name", brand.get("brand_name"))
        cls._append_key_value(lines, "Audience", brand.get("audience"))
        cls._append_list_values(lines, "Audience concerns addressed", brand.get("objections") or [], item_label="Concern")
        cls._append_brand_section_usage_lines(
            lines,
            cls._brand_section_usage_for_stage(payload, "content_generation"),
            heading="- Brand space sections used in content generation:",
        )
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Form Data Used")
        cls._append_key_value(lines, "Selected persona", request.get("persona_name"))
        cls._append_key_value(lines, "Persona role", request.get("persona_role"))
        cls._append_key_value(lines, "Selected objective", request.get("objective_name"))
        cls._append_key_value(lines, "Selected objective description", request.get("objective_description"))
        cls._append_key_value(lines, "Selected format", request.get("format"))
        cls._append_key_value(lines, "Selected platform", request.get("platform"))
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Template or Sample Data Used")
        cls._append_list_values(lines, "Content patterns adapted", sample_influence, item_label="Pattern")
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Content Used")
        cls._append_key_value(lines, "Headline", headline)
        cls._append_key_value(lines, "Body", body)
        cls._append_key_value(lines, "Call to action", cta)
        cls._append_list_values(lines, "Important keywords", keywords, item_label="Keyword")
        cls._append_list_values(lines, "Content rules followed", rules, item_label="Rule")
        cls._ensure_section_content(lines, section_start)
        cls._append_intelligence_evidence(lines, payload, "content_generation")
        cls._append_brand_following_score(lines, payload)
        return "\n".join(lines)

    @classmethod
    def _layout_stage_summary(cls, payload: dict[str, Any]) -> str:
        output = payload.get("layout_planning_output") if isinstance(payload.get("layout_planning_output"), dict) else {}
        sample_influence = cls._extract_sample_influence(payload)
        decision = output.get("layout_decision_used") if isinstance(output.get("layout_decision_used"), dict) else {}
        blueprint = output.get("blueprint_used") if isinstance(output.get("blueprint_used"), dict) else {}
        mode = str(decision.get("mode") or "").strip()
        layout_type = str(blueprint.get("layout_type") or "").strip()
        zone_roles = cls._dedupe_texts([str(item).strip().replace("_", " ") for item in (blueprint.get("zone_roles") or []) if str(item or "").strip()], limit=7)
        reasoning = cls._dedupe_texts([str(item).strip() for item in (decision.get("reasoning") or []) if str(item or "").strip()], limit=2)

        lines = ["Layout Planning"]
        brand = cls._extract_brand_context(payload)
        request = cls._extract_request_context(payload)
        human_layout_type = "image-led social" if layout_type == "image_led_social" else layout_type.replace("_", " ")

        section_start = len(lines)
        cls._start_section(lines, "Brand Data Used")
        cls._append_key_value(lines, "Brand name", brand.get("brand_name"))
        cls._append_key_value(lines, "Audience", brand.get("audience"))
        cls._append_brand_section_usage_lines(
            lines,
            cls._brand_section_usage_for_stage(payload, "layout_planning"),
            heading="- Brand space sections used in layout planning:",
        )
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Form Data Used")
        cls._append_key_value(lines, "Selected persona", request.get("persona_name"))
        cls._append_key_value(lines, "Persona role", request.get("persona_role"))
        cls._append_key_value(lines, "Selected objective", request.get("objective_name"))
        cls._append_key_value(lines, "Selected objective description", request.get("objective_description"))
        cls._append_key_value(lines, "Selected format", request.get("format"))
        cls._append_key_value(lines, "Selected platform", request.get("platform"))
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Template or Sample Data Used")
        cls._append_list_values(lines, "Content patterns adapted", sample_influence, item_label="Pattern")
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Layout Content Used")
        cls._append_key_value(lines, "Layout type", human_layout_type if human_layout_type else "")
        cls._append_key_value(lines, "Layout mode", mode.replace("_", " ") if mode else "")
        cls._append_list_values(lines, "Content zones used", zone_roles, item_label="Zone")
        if mode == "adapted_template":
            cls._append_key_value(lines, "Structure source", "Adapted from an existing reference layout")
        else:
            cls._append_list_values(lines, "Layout reasoning", reasoning, item_label="Reason")
        palette = cls._palette_usage_summary(payload, "layout_planning")
        cls._append_key_value(lines, "Primary color", palette.get("primary"))
        cls._append_key_value(lines, "Secondary color", palette.get("secondary"))
        cls._append_key_value(lines, "Tertiary color", palette.get("tertiary"))
        cls._append_key_value(lines, "Accent color", palette.get("accent"))
        cls._append_key_value(lines, "Background color", palette.get("background"))
        cls._append_list_values(lines, "Additional palette", palette.get("additional") or [], item_label="Color")
        cls._ensure_section_content(lines, section_start)
        cls._append_intelligence_evidence(lines, payload, "layout_planning")
        cls._append_brand_following_score(lines, payload)
        return "\n".join(lines)

    @classmethod
    def _visual_stage_summary(cls, payload: dict[str, Any]) -> str:
        visual = payload.get("visual_content_used_for_image_generation") if isinstance(payload.get("visual_content_used_for_image_generation"), dict) else {}
        plan = visual.get("visual_plan_used") if isinstance(visual.get("visual_plan_used"), dict) else {}
        content = visual.get("visual_content_used") if isinstance(visual.get("visual_content_used"), dict) else {}

        generated_direction = ""
        for key in ("generated_visual_direction", "image_prompt", "visual_direction", "content_summary"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                generated_direction = cls._repair_encoding_noise(value.strip())
                break
        if not generated_direction:
            selected = content.get("selected_reference_images")
            if isinstance(selected, list):
                for item in selected:
                    if isinstance(item, dict):
                        generated_direction = cls._clean_reference_content(str(item.get("content_summary") or ""))
                        if generated_direction:
                            break

        reference_notes: list[str] = []
        for key in ("selected_reference_images", "conditioning_reference_images", "provided_reference_content"):
            items = content.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                cleaned = cls._clean_reference_content(str(item.get("content_summary") or ""))
                if cleaned:
                    reference_notes.append(cleaned)

        lines = ["Visual Planning"]
        request = cls._extract_request_context(payload)
        brand = cls._extract_brand_context(payload)
        plan_text: list[str] = []
        if plan.get("page_strategy"):
            plan_text.append(str(plan.get("page_strategy")).replace("_", " "))
        if plan.get("visual_sequence_expectation"):
            plan_text.append(str(plan.get("visual_sequence_expectation")).replace("_", " "))
        cleaned_refs = cls._dedupe_texts(reference_notes, limit=3)

        section_start = len(lines)
        cls._start_section(lines, "Brand Data Used")
        cls._append_key_value(lines, "Brand name", brand.get("brand_name"))
        cls._append_key_value(lines, "Audience", brand.get("audience"))
        cls._append_brand_section_usage_lines(
            lines,
            cls._brand_section_usage_for_stage(payload, "visual_planning"),
            heading="- Brand space sections used in visual planning:",
        )
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Form Data Used")
        cls._append_key_value(lines, "Selected format", request.get("format") or payload.get("format"))
        cls._append_key_value(lines, "Selected platform", request.get("platform"))
        cls._append_key_value(lines, "Selected persona", request.get("persona_name"))
        cls._append_key_value(lines, "Selected objective", request.get("objective_name"))
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Visual Content Used")
        cls._append_key_value(lines, "Visual direction", generated_direction)
        cls._append_key_value(lines, "Primary unit", plan.get("primary_unit"))
        cls._append_key_value(lines, "Density target", plan.get("density_target"))
        cls._append_list_values(lines, "Visual execution plan", plan_text, item_label="Mode")
        cls._append_list_values(lines, "Reference visual patterns", cleaned_refs, item_label="Pattern")
        palette = cls._palette_usage_summary(payload, "visual_planning")
        cls._append_key_value(lines, "Primary color", palette.get("primary"))
        cls._append_key_value(lines, "Secondary color", palette.get("secondary"))
        cls._append_key_value(lines, "Tertiary color", palette.get("tertiary"))
        cls._append_key_value(lines, "Accent color", palette.get("accent"))
        cls._append_key_value(lines, "Background color", palette.get("background"))
        cls._append_list_values(lines, "Additional palette", palette.get("additional") or [], item_label="Color")
        cls._ensure_section_content(lines, section_start)
        cls._append_intelligence_evidence(lines, payload, "visual_planning")
        cls._append_brand_following_score(lines, payload)
        return "\n".join(lines)

    @classmethod
    def _slide_stage_summary(cls, payload: dict[str, Any]) -> str:
        trace = payload.get("slide_or_section_trace") if isinstance(payload.get("slide_or_section_trace"), dict) else {}
        unit_type = str(trace.get("unit_type") or "panel").strip()
        units = trace.get("units") if isinstance(trace.get("units"), list) else []
        if not units:
            return cls._sentence_block([f"This stage prepared the {unit_type} content sequence for the image."])
        first_unit = units[0] if isinstance(units[0], dict) else {}
        brand = cls._extract_brand_context(payload)
        panel_goal = cls._repair_encoding_noise(str(first_unit.get("panel_goal") or "").strip())
        dominant_message = cls._repair_encoding_noise(str(first_unit.get("dominant_message") or first_unit.get("headline") or "").strip())
        supporting_lines = cls._dedupe_texts([str(item).strip() for item in (first_unit.get("supporting_lines") or []) if str(item or "").strip()], limit=3)
        proof_points = cls._dedupe_texts([str(item).strip() for item in (first_unit.get("proof_points") or []) if str(item or "").strip()], limit=3)
        stats = cls._dedupe_texts([str(item).strip() for item in (first_unit.get("stat_highlights") or []) if str(item or "").strip()], limit=2)
        visual_focus = cls._repair_encoding_noise(str(first_unit.get("visual_focus") or "").strip())
        cta = cls._repair_encoding_noise(str(first_unit.get("cta") or "").strip())

        lines = ["Slide Trace"]
        request = cls._extract_request_context(payload)

        section_start = len(lines)
        cls._start_section(lines, "Brand Data Used")
        cls._append_key_value(lines, "Brand name", brand.get("brand_name"))
        cls._append_key_value(lines, "Audience", brand.get("audience"))
        cls._append_brand_section_usage_lines(
            lines,
            cls._brand_section_usage_for_stage(payload, "slide_trace"),
            heading="- Brand space sections used in slide planning:",
        )
        cls._ensure_section_content(lines, section_start)

        section_start = len(lines)
        cls._start_section(lines, "Form Data Used")
        cls._append_key_value(lines, "Selected format", request.get("format") or payload.get("format"))
        cls._append_key_value(lines, "Selected platform", request.get("platform"))
        cls._append_key_value(lines, "Selected persona", request.get("persona_name"))
        cls._append_key_value(lines, "Selected objective", request.get("objective_name"))
        cls._append_key_value(lines, "Unit type", unit_type)
        cls._ensure_section_content(lines, section_start)

        for index, unit in enumerate(units, start=1):
            if not isinstance(unit, dict):
                continue
            unit_goal = cls._repair_encoding_noise(str(unit.get("panel_goal") or "").strip())
            unit_message = cls._repair_encoding_noise(str(unit.get("dominant_message") or unit.get("headline") or "").strip())
            unit_supporting = cls._dedupe_texts([str(item).strip() for item in (unit.get("supporting_lines") or []) if str(item or "").strip()], limit=4)
            unit_proof = cls._dedupe_texts([str(item).strip() for item in (unit.get("proof_points") or []) if str(item or "").strip()], limit=4)
            unit_stats = cls._dedupe_texts([str(item).strip() for item in (unit.get("stat_highlights") or []) if str(item or "").strip()], limit=3)
            unit_focus = cls._repair_encoding_noise(str(unit.get("visual_focus") or "").strip())
            unit_cta = cls._repair_encoding_noise(str(unit.get("cta") or "").strip())
            section_start = len(lines)
            title = f"Slide {index} Content Used" if unit_type != "panel" else f"Panel {index} Content Used"
            cls._start_section(lines, title)
            cls._append_key_value(lines, "Goal", unit_goal)
            cls._append_key_value(lines, "Dominant message", unit_message)
            cls._append_key_value(lines, "Headline", cls._repair_encoding_noise(str(unit.get("headline") or "").strip()))
            cls._append_key_value(lines, "Body", cls._repair_encoding_noise(str(unit.get("body") or "").strip()))
            cls._append_key_value(lines, "Call to action", unit_cta)
            cls._append_list_values(lines, "Supporting lines", unit_supporting, item_label="Line")
            cls._append_list_values(lines, "Proof points", unit_proof, item_label="Point")
            cls._append_list_values(lines, "Stat highlights", unit_stats, item_label="Stat")
            cls._append_key_value(lines, "Visual focus", unit_focus)
            section_usage = cls._brand_section_usage_for_stage(payload, "slide_trace")
            cls._append_brand_section_usage_lines(
                lines,
                section_usage,
                heading="- Brand space sections adopted for this unit:",
            )
            cls._ensure_section_content(lines, section_start)
        cls._append_intelligence_evidence(lines, payload, "slide_trace")
        cls._append_brand_following_score(lines, payload)
        return "\n".join(lines)

    @classmethod
    def _build_stage_text_summary(cls, *, stage_name: str, payload: dict[str, Any]) -> str:
        if stage_name == "planning_strategy":
            return cls._planning_stage_summary(payload)
        elif stage_name == "content_generation":
            return cls._content_stage_summary(payload)
        elif stage_name == "layout_planning":
            return cls._layout_stage_summary(payload)
        elif stage_name == "visual_planning":
            return cls._visual_stage_summary(payload)
        elif stage_name == "slide_trace":
            return cls._slide_stage_summary(payload)
        return cls._repair_encoding_noise(cls._stage_title(stage_name))

    def _generate_stage_text_summary(self, *, stage_name: str, payload: dict[str, Any]) -> str:
        return self._build_stage_text_summary(stage_name=stage_name, payload=payload)

    def write_visual_generation_readable_text_bundle(
        self,
        trace_id: str | None,
        bundle: dict[str, dict[str, Any]] | None,
    ) -> list[str]:
        if not self.enabled or not trace_id or not isinstance(bundle, dict):
            return []
        target_dir = self.readable_visual_trace_dir(trace_id)
        written_files: list[str] = []
        for filename in (
            "planning_strategy",
            "content_generation",
            "layout_planning",
            "visual_planning",
            "slide_trace",
        ):
            payload = bundle.get(filename)
            if not isinstance(payload, dict):
                continue
            summary = self._generate_stage_text_summary(stage_name=filename, payload=payload)
            written = self._write_text_file(target_dir / f"{filename}.txt", summary)
            if written:
                written_files.append(written)
        if written_files:
            self.write_debug_event(
                "trace.write_visual_generation_text_bundle.succeeded",
                {
                    "trace_id": trace_id,
                    "target_dir": str(target_dir),
                    "file_count": len(written_files),
                },
            )
        return written_files

    @classmethod
    def build_visual_generation_readable_bundle(
        cls,
        *,
        trace_id: str,
        prompt: str,
        tenant_id: Any,
        brand_space_id: Any,
        studio_panel: dict[str, Any],
        request_payload: dict[str, Any],
        section_payloads: dict[str, Any],
        runtime_brand_context: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        reference_assets: list[dict[str, Any]],
        template_candidates: list[dict[str, Any]],
        template_context: dict[str, Any],
        retrieved_knowledge: dict[str, list[dict[str, Any]]],
        planning_hints: dict[str, Any],
        logo_candidates: list[dict[str, Any]],
        logo_selection: dict[str, Any] | None,
        generated_payload: dict[str, Any],
        blueprint_payload: dict[str, Any],
        explainability: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        explainability = explainability if isinstance(explainability, dict) else {}
        template_context = template_context if isinstance(template_context, dict) else {}
        research_editorial_brief = (
            explainability.get("research_editorial_brief")
            if isinstance(explainability.get("research_editorial_brief"), dict)
            else {}
        )
        content_plan = explainability.get("content_plan") if isinstance(explainability.get("content_plan"), dict) else {}
        visual_plan = explainability.get("visual_plan") if isinstance(explainability.get("visual_plan"), dict) else {}
        input_access_summary = (
            explainability.get("input_access_summary")
            if isinstance(explainability.get("input_access_summary"), dict)
            else {}
        )
        format_name = cls._normalize_format_name(studio_panel)
        common_sources = {
            "brand_data_used": cls._brand_data_used_summary(
                runtime_brand_context=runtime_brand_context,
                persona_context=persona_context,
                objective_context=objective_context,
                input_access_summary=input_access_summary,
            ),
            "form_data_used": cls._form_data_used_summary(
                prompt=prompt,
                studio_panel=studio_panel,
                request_payload=request_payload,
                persona_context=persona_context,
                objective_context=objective_context,
            ),
            "template_or_sample_data_used": cls._template_sample_data_summary(
                template_context=template_context,
                template_candidates=template_candidates,
                reference_assets=reference_assets,
                research_editorial_brief=research_editorial_brief,
                explainability=explainability,
            ),
        }
        brand_usage_snapshot = cls.build_brand_usage_report(
            trace_id=trace_id,
            mode="content.generate.readable_trace",
            prompt=prompt,
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            studio_panel=studio_panel,
            section_payloads=section_payloads,
            runtime_brand_context=runtime_brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            reference_assets=reference_assets,
            template_candidates=template_candidates,
            template_context=template_context,
            retrieved_knowledge=retrieved_knowledge,
            planning_hints=planning_hints,
            explainability=explainability,
            selected_template={
                "template_id": str(
                    template_context.get("selected_template_id")
                    or template_context.get("template_id")
                    or ""
                ),
                "template_name": str(
                    template_context.get("selected_template_name")
                    or template_context.get("template_name")
                    or ""
                ),
            },
            logo_candidates=logo_candidates,
            logo_selection=logo_selection,
        )
        compliance_summary = cls._validation_summary(explainability)
        full_trace_logs = {
            "trace_manifest": {
                "trace_id": trace_id,
                "tenant_id": str(tenant_id),
                "brand_space_id": str(brand_space_id),
                "prompt": prompt,
                "studio_panel": studio_panel,
            },
            "request_payload": request_payload,
            "section_payloads": section_payloads,
            "runtime_brand_context": runtime_brand_context,
            "persona_context": persona_context,
            "objective_context": objective_context,
            "reference_assets": reference_assets,
            "template_candidates": template_candidates,
            "template_context": template_context,
            "retrieved_knowledge": retrieved_knowledge,
            "planning_hints": planning_hints,
            "logo_candidates": logo_candidates,
            "logo_selection": logo_selection or {},
            "generated_payload": generated_payload,
            "blueprint_payload": blueprint_payload,
            "brand_usage_snapshot": brand_usage_snapshot,
            "input_access_summary": input_access_summary,
            "compiled_context": (
                explainability.get("compiled_context")
                if isinstance(explainability.get("compiled_context"), dict)
                else {}
            ),
            "selected_reference_images": explainability.get("selected_reference_images") or [],
            "conditioning_reference_images": explainability.get("conditioning_reference_images") or [],
            "generation_trace": (
                explainability.get("generation_trace")
                if isinstance(explainability.get("generation_trace"), dict)
                else {}
            ),
            "validation_summary": compliance_summary,
            "explainability_snapshot": explainability,
        }
        bundle = {
            "planning_strategy": {
                "trace_id": trace_id,
                "format": format_name,
                "stage": "planning_strategy",
                "data_passed_for_image_generation": common_sources,
                "full_trace_logs": full_trace_logs,
                "strategy_output": cls._planning_strategy_output(research_editorial_brief),
                "brand_evaluation_and_compliance": compliance_summary,
            },
            "content_generation": {
                "trace_id": trace_id,
                "format": format_name,
                "stage": "content_generation",
                "data_passed_for_image_generation": common_sources,
                "full_trace_logs": full_trace_logs,
                "content_generation_output": cls._content_generation_output(
                    content_plan=content_plan,
                    generated_payload=generated_payload,
                    explainability=explainability,
                    format_name=format_name,
                ),
                "brand_evaluation_and_compliance": compliance_summary,
            },
            "layout_planning": {
                "trace_id": trace_id,
                "format": format_name,
                "stage": "layout_planning",
                "data_passed_for_image_generation": common_sources,
                "full_trace_logs": full_trace_logs,
                "layout_planning_output": cls._layout_planning_output(
                    planning_hints=planning_hints,
                    blueprint_payload=blueprint_payload,
                    explainability=explainability,
                ),
                "brand_evaluation_and_compliance": compliance_summary,
            },
            "visual_planning": {
                "trace_id": trace_id,
                "format": format_name,
                "stage": "visual_planning",
                "data_passed_for_image_generation": common_sources,
                "full_trace_logs": full_trace_logs,
                "visual_content_used_for_image_generation": cls._visual_content_used_summary(
                    visual_plan=visual_plan,
                    reference_assets=reference_assets,
                    generated_payload=generated_payload,
                    explainability=explainability,
                    format_name=format_name,
                ),
                "brand_evaluation_and_compliance": compliance_summary,
            },
            "slide_trace": {
                "trace_id": trace_id,
                "format": format_name,
                "stage": "slide_trace",
                "data_passed_for_image_generation": common_sources,
                "full_trace_logs": full_trace_logs,
                "slide_or_section_trace": cls._slide_trace_output(
                    format_name=format_name,
                    generated_payload=generated_payload,
                    research_editorial_brief=research_editorial_brief,
                    content_plan=content_plan,
                    template_context=template_context,
                ),
                "brand_evaluation_and_compliance": compliance_summary,
            },
        }
        for stage_name, payload in bundle.items():
            if not isinstance(payload, dict):
                continue
            payload["intelligence_evidence"] = cls._intelligence_evidence(stage_name, payload)
        return bundle

    def write_visual_generation_readable_bundle(
        self,
        trace_id: str | None,
        bundle: dict[str, dict[str, Any]] | None,
    ) -> list[str]:
        if not self.enabled or not trace_id or not isinstance(bundle, dict):
            return []
        target_dir = self.readable_visual_trace_dir(trace_id)
        written_files: list[str] = []
        for filename in (
            "planning_strategy",
            "content_generation",
            "layout_planning",
            "visual_planning",
            "slide_trace",
        ):
              payload = bundle.get(filename)
              if not isinstance(payload, dict):
                  continue
              written = self._write_json_file(target_dir / f"{filename}.json", payload)
              if written:
                  written_files.append(written)
        text_files = self.write_visual_generation_readable_text_bundle(trace_id, bundle)
        written_files.extend(text_files)
        if written_files:
            self.write_debug_event(
                "trace.write_visual_generation_bundle.succeeded",
                {
                    "trace_id": trace_id,
                    "target_dir": str(target_dir),
                    "file_count": len(written_files),
                },
            )
        return written_files
