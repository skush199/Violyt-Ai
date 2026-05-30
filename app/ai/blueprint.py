from __future__ import annotations

from typing import Any

from app.ai.contracts import BlueprintPayload, BlueprintZone, GenerationSceneGraph, SceneGraphElement


class BlueprintService:
    PRESET_DIMENSIONS = {
        "instagram": {"width": 1080, "height": 1080},
        "linkedin": {"width": 1200, "height": 627},
        "x": {"width": 1600, "height": 900},
        "youtube_thumbnail": {"width": 1280, "height": 720},
    }

    @staticmethod
    def _scene_element_zone(
        element: SceneGraphElement,
        *,
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any] | None:
        geometry = element.geometry
        width_value = geometry.width
        height_value = geometry.height
        x_value = geometry.x
        y_value = geometry.y
        if width_value is None or height_value is None:
            return None

        def _resolve(value: float | int | None, scale: int) -> int:
            if value is None:
                return 0
            numeric = float(value)
            if geometry.units == "normalized" and 0 <= numeric <= 1:
                return max(int(round(numeric * scale)), 0)
            return max(int(round(numeric)), 0)

        role = str(element.role or element.element_type)
        zone_id = str(element.element_id or role)
        anchor_defaults = {
            "top-left": (0.08, 0.08),
            "top-center": (0.5, 0.08),
            "top-right": (0.82, 0.08),
            "center-left": (0.08, 0.46),
            "center": (0.5, 0.46),
            "center-right": (0.82, 0.46),
            "bottom-left": (0.08, 0.84),
            "bottom-center": (0.5, 0.84),
            "bottom-right": (0.82, 0.84),
        }
        resolved_width = _resolve(width_value, canvas_width)
        resolved_height = _resolve(height_value, canvas_height)
        resolved_x = _resolve(x_value, canvas_width) if x_value is not None else 0
        resolved_y = _resolve(y_value, canvas_height) if y_value is not None else 0
        if geometry.anchor and (x_value is None or y_value is None):
            anchor_x, anchor_y = anchor_defaults.get(geometry.anchor, (0.08, 0.08))
            if x_value is None:
                resolved_x = max(int(round((anchor_x * canvas_width) - (resolved_width / 2))), 0)
            if y_value is None:
                resolved_y = max(int(round((anchor_y * canvas_height) - (resolved_height / 2))), 0)
        return {
            "zone_id": zone_id,
            "role": role,
            "x": resolved_x,
            "y": resolved_y,
            "width": resolved_width,
            "height": resolved_height,
            "max_lines": element.style.get("max_lines") if isinstance(element.style, dict) else None,
        }

    def build(
        self,
        text_payload: dict[str, Any],
        studio_panel: dict[str, Any],
        template_metadata: dict[str, Any] | None = None,
        layout_decision: dict[str, Any] | None = None,
        brand_context: dict[str, Any] | None = None,
    ) -> BlueprintPayload:
        preset = studio_panel.get("platform_preset", "instagram")
        layout_type = studio_panel.get("format", "static")
        size = studio_panel.get("size") or self.PRESET_DIMENSIONS.get(preset, self.PRESET_DIMENSIONS["instagram"])
        width = size["width"]
        height = size["height"]
        decision = layout_decision or {}
        mode = str(decision.get("mode") or "synthesized_layout")
        adaptation_plan = dict(decision.get("adaptation_plan") or {})
        context = brand_context or {}
        metadata = text_payload.get("metadata", {}) if isinstance(text_payload.get("metadata"), dict) else {}
        content_structure = metadata.get("content_structure", {}) if isinstance(metadata.get("content_structure"), dict) else {}
        zone_load = content_structure.get("zone_load", {}) if isinstance(content_structure.get("zone_load"), dict) else {}

        zone_map = (template_metadata or {}).get("zone_map") or {}
        if mode in {"exact_template", "adapted_template"} and zone_map.get("layout_type"):
            layout_type = str(zone_map.get("layout_type"))
        pad_x = max(48, int(width * 0.06))
        pad_y = max(40, int(height * 0.06))
        logo_width = max(140, int(width * 0.16))
        logo_height = max(60, int(height * 0.1))
        headline_height = max(140, int(height * 0.2))
        cta_height = max(88, int(height * 0.12))

        if preset in {"linkedin", "x", "youtube_thumbnail"}:
            image_width = int(width * 0.34)
            headline_width = width - (pad_x * 2) - image_width - 24
            body_top = pad_y + headline_height + 18
            body_height = max(140, height - body_top - cta_height - pad_y - 32)
            default_zones = [
                BlueprintZone(zone_id="logo", role="logo", x=width - pad_x - logo_width, y=pad_y, width=logo_width, height=logo_height),
                BlueprintZone(zone_id="headline", role="headline", x=pad_x, y=pad_y, width=headline_width, height=headline_height, max_lines=3),
                BlueprintZone(zone_id="body", role="body", x=pad_x, y=body_top, width=headline_width, height=body_height, max_lines=7),
                BlueprintZone(zone_id="image", role="image", x=width - pad_x - image_width, y=pad_y + logo_height + 18, width=image_width, height=max(220, int(height * 0.56))),
                BlueprintZone(zone_id="cta", role="cta", x=pad_x, y=height - pad_y - cta_height, width=min(360, headline_width), height=cta_height, max_lines=2),
            ]
        else:
            image_height = max(280, int(height * 0.34))
            headline_top = pad_y + logo_height + 12
            body_top = headline_top + headline_height + 12
            image_top = body_top + max(140, int(height * 0.2)) + 12
            default_zones = [
                BlueprintZone(zone_id="logo", role="logo", x=width - pad_x - logo_width, y=pad_y, width=logo_width, height=logo_height),
                BlueprintZone(zone_id="headline", role="headline", x=pad_x, y=headline_top, width=width - (pad_x * 2), height=headline_height, max_lines=3),
                BlueprintZone(zone_id="body", role="body", x=pad_x, y=body_top, width=width - (pad_x * 2), height=max(160, int(height * 0.2)), max_lines=7),
                BlueprintZone(zone_id="image", role="image", x=pad_x, y=image_top, width=width - (pad_x * 2), height=image_height),
                BlueprintZone(zone_id="cta", role="cta", x=pad_x, y=height - pad_y - cta_height, width=min(420, width - (pad_x * 2)), height=cta_height, max_lines=2),
            ]
        raw_zones = zone_map.get("zones") or [zone.model_dump() for zone in default_zones]
        if mode == "adapted_template" and zone_map.get("zones"):
            raw_zones = self._adapt_template_zones(
                raw_zones,
                width=width,
                height=height,
                text_payload=text_payload,
                adaptation_plan=adaptation_plan,
            )
        normalized_zones = self.resolve_zone_payloads(
            raw_zones,
            default_zones,
            canvas_size={"width": width, "height": height},
        )
        zones = [BlueprintZone(**zone) if isinstance(zone, dict) else zone for zone in normalized_zones]
        brand_rules_applied = self._brand_rules_applied(context)

        return BlueprintPayload(
            layout_type=layout_type,
            zones=zones,
            hierarchy=["headline", "body", "cta", "logo"],
            text_blocks=[
                {"role": "headline", "text": text_payload.get("headline", "")},
                {"role": "body", "text": text_payload.get("body", "")},
                {"role": "cta", "text": text_payload.get("cta", "")},
            ],
            image_zones=[{"role": "primary_visual", "zone_id": "image", "required": layout_type not in {"doc", "pdf"}}],
            logo_rules={"zone_id": "logo", "required": True, "fit_mode": "contain"},
            cta_placement={"zone_id": "cta", "alignment": "left"},
            platform_preset=preset,
            export_format=studio_panel.get("file_type", "png"),
            overflow_strategy={"mode": "shrink_then_wrap", "deterministic": True},
            source_mode=mode,
            source_template_id=str(decision.get("template_id")) if decision.get("template_id") else None,
            layout_archetype="template_lock" if mode == "exact_template" else ("template_adapt" if mode == "adapted_template" else None),
            adaptation_plan=adaptation_plan,
            brand_rules_applied=brand_rules_applied,
            composition_plan={
                "content_structure": content_structure,
                "zone_load": zone_load,
            },
        )

    def from_scene_graph(
        self,
        scene_graph: GenerationSceneGraph,
        *,
        studio_panel: dict[str, Any],
        text_payload: dict[str, Any] | None = None,
        brand_rules_applied: dict[str, Any] | None = None,
    ) -> BlueprintPayload:
        canvas = scene_graph.canvas
        compatible_roles = {
            "headline",
            "supporting_line",
            "body",
            "proof_points",
            "cta",
            "logo",
            "image",
            "footer",
            "legal",
        }
        raw_zones = [
            zone
            for element in scene_graph.elements
            if element.visible and element.role in compatible_roles
            for zone in [self._scene_element_zone(element, canvas_width=canvas.width, canvas_height=canvas.height)]
            if zone
        ]
        default_blueprint = self.build(
            text_payload=text_payload or {"headline": "", "body": "", "cta": ""},
            studio_panel=studio_panel,
            template_metadata=None,
            layout_decision={
                "mode": scene_graph.layout_mode,
                "adaptation_plan": scene_graph.template_adaptation,
            },
            brand_context={},
        )
        zones = self.resolve_zone_payloads(
            raw_zones or [zone.model_dump() for zone in default_blueprint.zones],
            default_blueprint.zones,
            canvas_size={"width": canvas.width, "height": canvas.height},
        )
        text_blocks = []
        for role in ("headline", "supporting_line", "body", "proof_points", "cta", "footer", "legal"):
            element = next((item for item in scene_graph.elements if item.visible and item.role == role), None)
            if element and element.text:
                text_blocks.append({"role": role, "text": element.text})
        resolved_zone_id_by_role: dict[str, str] = {
            str(zone["role"]): str(zone["zone_id"])
            for zone in zones
            if zone.get("role") and zone.get("zone_id")
        }
        image_zones = [
            {
                "role": element.role,
                "zone_id": resolved_zone_id_by_role.get(str(element.role or ""), str(element.element_id or element.role or "")),
                "required": element.role == "image",
            }
            for element in scene_graph.elements
            if element.visible and element.role in {"image", "icon"}
        ]
        template_adaptation = scene_graph.template_adaptation or {}
        source_template_id = template_adaptation.get("selected_template_id")
        if scene_graph.layout_mode == "synthesized_layout" or template_adaptation.get("reference_style_only") or template_adaptation.get("topic_fit_too_weak"):
            source_template_id = None
        return BlueprintPayload(
            layout_type=str(scene_graph.styles.get("layout_type") or studio_panel.get("format") or "static"),
            zones=[BlueprintZone(**zone) for zone in zones],
            hierarchy=[zone["role"] for zone in zones],
            text_blocks=text_blocks,
            image_zones=image_zones,
            logo_rules={"zone_id": "logo", "required": any(zone["role"] == "logo" for zone in zones), "fit_mode": "contain"},
            cta_placement={"zone_id": "cta", "alignment": "left"},
            platform_preset=scene_graph.canvas.platform,
            export_format=scene_graph.canvas.file_type or studio_panel.get("file_type", "png"),
            overflow_strategy={"mode": "scene_graph_validate_then_wrap", "deterministic": True},
            source_mode=scene_graph.layout_mode,
            source_template_id=source_template_id,
            layout_archetype=str(scene_graph.styles.get("layout_archetype") or scene_graph.styles.get("layout_type") or ""),
            adaptation_plan=template_adaptation,
            brand_rules_applied=brand_rules_applied or {},
            composition_plan={"scene_graph_layers": scene_graph.layers, "scene_graph_styles": scene_graph.styles},
        )

    @staticmethod
    def resolve_zone_payloads(
        raw_zones: list[dict[str, Any]] | list[BlueprintZone] | None,
        default_zones: list[dict[str, Any]] | list[BlueprintZone],
        canvas_size: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        default_payloads = [
            zone.model_dump() if isinstance(zone, BlueprintZone) else dict(zone)
            for zone in default_zones
        ]
        canvas_width = int((canvas_size or {}).get("width") or 0)
        canvas_height = int((canvas_size or {}).get("height") or 0)
        if not canvas_width:
            canvas_width = max(
                (
                    int(zone.get("x", 0)) + int(zone.get("width", 0))
                    for zone in default_payloads
                    if zone.get("width") is not None
                ),
                default=0,
            )
        if not canvas_height:
            canvas_height = max(
                (
                    int(zone.get("y", 0)) + int(zone.get("height", 0))
                    for zone in default_payloads
                    if zone.get("height") is not None
                ),
                default=0,
            )
        fallback_by_role = {
            str(zone.get("role", "")): zone
            for zone in default_payloads
            if zone.get("role")
        }
        fallback_by_id = {
            str(zone.get("zone_id", "")): zone
            for zone in default_payloads
            if zone.get("zone_id")
        }
        if not raw_zones:
            return default_payloads

        resolved: list[dict[str, Any]] = []
        for index, raw_zone in enumerate(raw_zones):
            zone_payload = raw_zone.model_dump() if isinstance(raw_zone, BlueprintZone) else dict(raw_zone)
            role = str(zone_payload.get("role", ""))
            zone_id = str(zone_payload.get("zone_id", ""))
            fallback = (
                fallback_by_role.get(role)
                or fallback_by_id.get(zone_id)
                or default_payloads[min(index, len(default_payloads) - 1)]
            )
            merged = dict(fallback)
            merged.update({key: value for key, value in zone_payload.items() if value is not None})
            for key in ("x", "y", "width", "height"):
                raw_value = merged.get(key)
                if not isinstance(raw_value, (int, float)):
                    continue
                numeric = float(raw_value)
                if 0 <= numeric <= 1:
                    scale = canvas_width if key in {"x", "width"} else canvas_height
                    merged[key] = max(int(round(numeric * scale)), 0)
                else:
                    merged[key] = max(int(round(numeric)), 0)
            resolved.append(merged)
        return resolved

    @staticmethod
    def _adapt_template_zones(
        zones: list[dict[str, Any]],
        *,
        width: int,
        height: int,
        text_payload: dict[str, Any],
        adaptation_plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        adjusted = [dict(zone) for zone in zones]
        role_map = {
            str(zone.get("role")): zone
            for zone in adjusted
            if isinstance(zone, dict) and zone.get("role")
        }
        headline_zone = role_map.get("headline")
        body_zone = role_map.get("body")
        image_zone = role_map.get("image")
        cta_zone = role_map.get("cta")

        headline_length = len(str(text_payload.get("headline", "")).strip())
        body_length = len(str(text_payload.get("body", "")).strip())
        metadata = text_payload.get("metadata", {}) if isinstance(text_payload.get("metadata"), dict) else {}
        content_structure = metadata.get("content_structure", {}) if isinstance(metadata.get("content_structure"), dict) else {}
        zone_load = content_structure.get("zone_load", {}) if isinstance(content_structure.get("zone_load"), dict) else {}
        proof_count = int(zone_load.get("proof_point_count") or 0)
        stat_count = int(zone_load.get("stat_count") or 0)
        text_density = str(zone_load.get("text_density") or "").strip().lower()

        if headline_zone and (adaptation_plan.get("expand_headline_or_body") or headline_length > 72):
            increase = min(max(int(headline_zone.get("height", 0) * 0.2), 32), int(height * 0.12))
            headline_zone["height"] = headline_zone.get("height", 0) + increase
            if body_zone and body_zone.get("y", 0) > headline_zone.get("y", 0):
                body_zone["y"] = body_zone.get("y", 0) + increase
                body_zone["height"] = max(body_zone.get("height", 0) - increase, 96)
            elif image_zone and image_zone.get("y", 0) > headline_zone.get("y", 0):
                image_zone["y"] = image_zone.get("y", 0) + increase
                image_zone["height"] = max(image_zone.get("height", 0) - increase, 140)

        if body_zone and (adaptation_plan.get("multi_section_flow") or body_length > 240):
            body_zone["max_lines"] = max(int(body_zone.get("max_lines") or 7), 9)
            if image_zone:
                image_zone["height"] = max(int(image_zone.get("height", 0) * 0.82), 160)
                image_zone["width"] = max(int(image_zone.get("width", 0) * 0.92), 180)

        if body_zone and (text_density == "high" or (proof_count + stat_count) >= 4):
            body_zone["max_lines"] = max(int(body_zone.get("max_lines") or 7), 10)
            body_zone["height"] = min(body_zone.get("height", 0) + max(int(height * 0.06), 48), height - int(body_zone.get("y", 0)) - 96)
            if image_zone:
                image_zone["height"] = max(int(image_zone.get("height", 0) * 0.74), 140)
                image_zone["width"] = max(int(image_zone.get("width", 0) * 0.88), 160)

        if cta_zone and adaptation_plan.get("compact_cta"):
            cta_zone["width"] = min(cta_zone.get("width", 0), max(int(width * 0.24), 220))
            cta_zone["height"] = min(cta_zone.get("height", 0), 84)

        if cta_zone and adaptation_plan.get("cta_reposition"):
            cta_zone["y"] = min(max(height - cta_zone.get("height", 0) - 48, 0), height - 24)

        return adjusted

    @staticmethod
    def _brand_rules_applied(brand_context: dict[str, Any]) -> dict[str, Any]:
        identity = brand_context.get("identity", {}) or {}
        visual_identity = brand_context.get("visual_identity", {}) or {}
        guardrails = brand_context.get("guardrails", {}) or {}
        typography = visual_identity.get("typography", {}) or {}
        return {
            "logo_required": bool(identity.get("logo_asset_id") or identity.get("logo_asset_ids") or identity.get("logo_assets")),
            "palette_roles": visual_identity.get("brand_color_palette", {}) or {},
            "font_families": [family.get("name") for family in typography.get("font_families", []) if family.get("name")],
            "restricted_topics": guardrails.get("restricted_topics", []),
            "blocked_words": guardrails.get("blocked_words", []),
        }
