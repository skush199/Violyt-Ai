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

    def __init__(self, base_dir: str | Path | None = None, enabled: bool | None = None) -> None:
        settings = get_settings()
        self.enabled = settings.generation_trace_enabled if enabled is None else enabled
        resolved_base = base_dir or settings.generation_trace_base_path
        self.base_dir = Path(resolved_base)
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
                    "display_name": str(item.get("display_name") or ""),
                    "score": item.get("score"),
                    "match_type": str(item.get("match_type") or ""),
                    "decision_confidence": item.get("decision_confidence"),
                    "format_family": str(item.get("format_family") or ""),
                    "is_primary_adaptation": bool(item.get("is_primary_adaptation")),
                    "selection_reason": str(item.get("selection_reason") or ""),
                    "recommendation_group_key": str(item.get("recommendation_group_key") or ""),
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
