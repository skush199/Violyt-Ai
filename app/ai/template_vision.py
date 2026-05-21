from __future__ import annotations

import base64
from collections import Counter
import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.core.config import get_settings


class TemplateVisionAnalyzer:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.model = settings.vision_model

    def analyze(self, image_path: str, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.client:
            return fallback
        path = Path(image_path)
        if not path.exists():
            return fallback
        try:
            encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a master brand designer performing a deep structural audit of a design sample. "
                            "Analyze the image and return JSON only with these specific keys: \n"
                            "1. background_style: {type: 'gradient'|'flat'|'image', description, primary_hex, secondary_hex, texture_hint}\n"
                            "2. layout_type: infographic, marketing_social, or product_post\n"
                            "3. editable_zones: Array of {role: 'headline'|'body'|'image'|'logo'|'cta', x, y, w, h}\n"
                            "4. typography_dna: {\n"
                            "     heading_style: 'bold_modern'|'classic_serif'|'minimal_sans',\n"
                            "     weight_hierarchy: string,\n"
                            "     text_alignment: 'left'|'center'|'right',\n"
                            "     dominant_case: 'uppercase'|'title'|'sentence'|'mixed',\n"
                            "     emphasis_pattern: 'headline_first'|'visual_first'|'balanced',\n"
                            "     font_size_palette: {headline_pt: number, subheading_pt: number, body_pt: number, caption_pt: number, footer_pt: number},\n"
                            "     line_heights: {headline: number, body: number}\n"
                            "   }\n"
                            "5. component_motifs: {\n"
                            "     cards: boolean,\n"
                            "     shadows: 'soft'|'hard'|'none',\n"
                            "     glassmorphism: boolean,\n"
                            "     borders: 'rounded'|'sharp',\n"
                            "     numbered_badges: {detected: boolean, shape: 'circle'|'rounded_rect'|'square', badge_color: string, text_color: string, has_numbers: boolean, number_format: '01'|'1'},\n"
                            "     text_background_boxes: {detected: boolean, applies_to: ['subheading'|'section_label'|'supporting_line'], box_color: string, border_radius: 'sharp'|'rounded'|'pill'},\n"
                            "     cta_button_style: {detected: boolean, style: 'solid'|'outlined'|'ghost'|'gradient', button_color: string, text_color: string, border_radius: number, has_icon: boolean},\n"
                            "     list_decorations: {style: 'bullets'|'numbers'|'icons'|'badges', color: string, custom_icon: boolean}\n"
                            "   }\n"
                            "6. visual_mood: overall emotional feel (e.g. premium, energetic, professional)\n"
                            "7. design_style: aesthetic movement (e.g. 3D, minimalist, flat, neo-brutalism)\n"
                            "8. infographic_elements: {graphs: 'circular'|'bar'|'none', icons: 'line'|'solid'|'3d', data_density: 'high'|'low'}\n"
                            "9. composition_rhythm: structural flow (e.g. asymmetrical, centered, grid, split-screen)\n"
                            "10. logo_anchor: typical placement (e.g. top_right, bottom_left)\n"
                            "11. visual_hierarchy: {\n"
                            "      focal_role: 'headline'|'image'|'cta'|'logo'|'mixed',\n"
                            "      reading_order: array of roles in order,\n"
                            "      density: 'airy'|'balanced'|'dense',\n"
                            "      whitespace: 'generous'|'moderate'|'tight',\n"
                            "      emphasis: 'headline_first'|'visual_first'|'balanced'\n"
                            "   }\n"
                            "12. content_structure: {\n"
                            "      headline_present: boolean,\n"
                            "      support_present: boolean,\n"
                            "      proof_modules: number,\n"
                            "      legal_footer_present: boolean,\n"
                            "      cta_prominence: 'high'|'medium'|'low',\n"
                            "      storytelling: 'single_claim'|'comparison'|'steps'|'benefit_stack'|'data_story'\n"
                            "   }\n"
                            "13. image_treatment: {\n"
                            "      style: 'photo'|'illustration'|'3d'|'iconic'|'abstract'|'mixed'|'none',\n"
                            "      crop: 'full_bleed'|'framed'|'cutout'|'none',\n"
                            "      subject_focus: 'single'|'multi'|'none'\n"
                            "   }\n"
                            "14. brand_cues: {\n"
                            "      tone_keywords: array of short strings,\n"
                            "      trust_markers: array of short strings,\n"
                            "      recurring_shapes: array of short strings,\n"
                            "      logo_lockup: 'standalone'|'with_wordmark'|'unknown'\n"
                            "   }\n"
                            "15. composition_logic: {\n"
                            "      balance: 'left_weighted'|'right_weighted'|'centered'|'symmetrical'|'asymmetrical'|'grid',\n"
                            "      framing: 'hero_center'|'split_panel'|'top_header_body'|'grid_modules'|'stacked_sections'|'mixed',\n"
                            "      layering: 'single_plane'|'layered'|'foreground_midground_background'|'stacked_cards',\n"
                            "      motion_flow: short string,\n"
                            "      focal_path: array of short role labels\n"
                            "   }\n"
                            "16. visual_craft_dna: {\n"
                            "      depth_style: 'flat'|'layered'|'3d_illusion'|'true_3d'|'mixed',\n"
                            "      rendering_style: 'vector'|'photo'|'3d_render'|'mixed',\n"
                            "      lighting: 'flat'|'soft'|'studio'|'ambient'|'mixed',\n"
                            "      polish_level: 'basic'|'clean'|'premium'|'editorial',\n"
                            "      material_cues: array of short strings,\n"
                            "      dimensionality_cues: array of short strings\n"
                            "   }\n"
                            "17. subject_semantics: {\n"
                            "      scene_type: short string,\n"
                            "      primary_subjects: array of short strings,\n"
                            "      domain_cues: array of short strings,\n"
                            "      financial_objects: array of short strings,\n"
                            "      human_presence: 'none'|'single'|'group'|'mixed',\n"
                            "      environment: short string,\n"
                            "      abstraction_level: 'literal'|'conceptual'|'symbolic'|'mixed'\n"
                            "   }\n"
                            "Coordinates MUST be normalized 0 to 1."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Perform a deep design audit. Return JSON only."},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{encoded}",
                            },
                        ],
                    },
                ],
                text={"format": {"type": "json_object"}},
            )
            parsed = json.loads(response.output_text or "{}")
            background_style = parsed.get("background_style", fallback.get("background_style", {}))
            if not isinstance(background_style, dict):
                background_style = {}
            background_type = str(
                background_style.get("type")
                or background_style.get("dominant_mode")
                or fallback.get("background_style", {}).get("type")
                or fallback.get("background_style", {}).get("dominant_mode")
                or "flat"
            ).strip()
            background_style = {
                **background_style,
                "type": background_type,
                "dominant_mode": background_type,
            }
            return {
                "background_style": background_style,
                "layout_type": parsed.get("layout_type", fallback.get("layout_type", "template")),
                "editable_zones": parsed.get("editable_zones", fallback.get("editable_zones", [])),
                "visual_mood": parsed.get("visual_mood", ""),
                "design_style": parsed.get("design_style", ""),
                "composition_style": parsed.get("composition_rhythm", parsed.get("composition_style", "")),
                "typography_dna": parsed.get("typography_dna", {}),
                "component_motifs": parsed.get("component_motifs", {}),
                "infographic_elements": parsed.get("infographic_elements", {}),
                "logo_anchor": parsed.get("logo_anchor", ""),
                "visual_hierarchy": parsed.get("visual_hierarchy", {}),
                "content_structure": parsed.get("content_structure", {}),
                "image_treatment": parsed.get("image_treatment", {}),
                "brand_cues": parsed.get("brand_cues", {}),
                "composition_logic": parsed.get("composition_logic", {}),
                "visual_craft_dna": parsed.get("visual_craft_dna", {}),
                "subject_semantics": parsed.get("subject_semantics", {}),
                "icons": parsed.get("icons", []),
                "platform_hints": parsed.get("platform_hints", []),
            }
        except Exception:  # noqa: BLE001
            return fallback

    @staticmethod
    def _merge_string_vote(values: list[Any]) -> str:
        normalized = [str(value).strip() for value in values if str(value).strip()]
        if not normalized:
            return ""
        counts = Counter(item.casefold() for item in normalized)
        first_seen: dict[str, str] = {}
        for item in normalized:
            first_seen.setdefault(item.casefold(), item)
        best_key = max(counts.items(), key=lambda item: (item[1], first_seen[item[0]]))[0]
        return first_seen[best_key]

    @classmethod
    def _merge_mapping_vote(cls, mappings: list[dict[str, Any]], *, keys: list[str]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for key in keys:
            values = [mapping.get(key) for mapping in mappings if isinstance(mapping, dict) and mapping.get(key) not in (None, "", [], {})]
            if not values:
                continue
            sample = values[0]
            if isinstance(sample, bool) and all(isinstance(value, bool) for value in values):
                merged[key] = sum(1 for value in values if value) >= max(1, len(values) // 2 + (len(values) % 2))
                continue
            if isinstance(sample, (int, float)) and all(isinstance(value, (int, float)) for value in values):
                merged[key] = round(sum(float(value) for value in values) / len(values), 2)
            elif isinstance(sample, list):
                deduped: list[Any] = []
                seen: set[str] = set()
                for item in values:
                    for nested in item if isinstance(item, list) else [item]:
                        marker = json.dumps(nested, sort_keys=True, ensure_ascii=True) if isinstance(nested, (dict, list)) else str(nested)
                        if marker in seen:
                            continue
                        seen.add(marker)
                        deduped.append(nested)
                merged[key] = deduped
            else:
                merged[key] = cls._merge_string_vote(values)
        return merged

    @classmethod
    def analyze_pages(
        cls,
        analyzer: "TemplateVisionAnalyzer",
        image_paths: list[str],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        selected = [str(path) for path in image_paths if str(path).strip()]
        if not selected:
            return fallback

        page_results: list[dict[str, Any]] = []
        page_summaries: list[dict[str, Any]] = []
        for index, image_path in enumerate(selected, start=1):
            result = analyzer.analyze(image_path, fallback)
            if not isinstance(result, dict):
                continue
            page_results.append(result)
            page_summaries.append(
                {
                    "page_index": index,
                    "image_path": image_path,
                    "layout_type": result.get("layout_type"),
                    "visual_mood": result.get("visual_mood"),
                    "design_style": result.get("design_style"),
                    "editable_zone_count": len(result.get("editable_zones", []) or []),
                }
            )

        if not page_results:
            return fallback

        primary = max(
            page_results,
            key=lambda item: (
                len(item.get("editable_zones", []) or []),
                len(item.get("component_motifs", {}) or {}),
                len(item.get("visual_hierarchy", {}) or {}),
            ),
        )

        background_candidates = [item.get("background_style") for item in page_results if isinstance(item.get("background_style"), dict)]
        typography_candidates = [item.get("typography_dna") for item in page_results if isinstance(item.get("typography_dna"), dict)]
        hierarchy_candidates = [item.get("visual_hierarchy") for item in page_results if isinstance(item.get("visual_hierarchy"), dict)]
        content_structure_candidates = [item.get("content_structure") for item in page_results if isinstance(item.get("content_structure"), dict)]
        image_treatment_candidates = [item.get("image_treatment") for item in page_results if isinstance(item.get("image_treatment"), dict)]
        brand_cue_candidates = [item.get("brand_cues") for item in page_results if isinstance(item.get("brand_cues"), dict)]
        infographic_candidates = [item.get("infographic_elements") for item in page_results if isinstance(item.get("infographic_elements"), dict)]
        composition_logic_candidates = [item.get("composition_logic") for item in page_results if isinstance(item.get("composition_logic"), dict)]
        visual_craft_candidates = [item.get("visual_craft_dna") for item in page_results if isinstance(item.get("visual_craft_dna"), dict)]
        subject_semantic_candidates = [item.get("subject_semantics") for item in page_results if isinstance(item.get("subject_semantics"), dict)]

        component_motifs: dict[str, Any] = {}
        motif_support: Counter[str] = Counter()
        for result in page_results:
            motifs = result.get("component_motifs") if isinstance(result.get("component_motifs"), dict) else {}
            for key, value in motifs.items():
                if not value:
                    continue
                if isinstance(value, dict) and value.get("detected") is False:
                    continue
                motif_support[key] += 1
                existing = component_motifs.get(key, {})
                if not existing or (isinstance(value, dict) and len(value) >= len(existing)):
                    component_motifs[key] = value
        for key, value in tuple(component_motifs.items()):
            if isinstance(value, dict):
                component_motifs[key] = {
                    **value,
                    "page_support": motif_support.get(key, 0),
                    "page_support_ratio": round(motif_support.get(key, 0) / max(len(page_results), 1), 4),
                }

        merged = {
            **primary,
            "background_style": {
                **(background_candidates[0] if background_candidates else {}),
                **cls._merge_mapping_vote(background_candidates, keys=["type", "dominant_mode", "description", "primary_hex", "secondary_hex", "texture_hint"]),
            } if background_candidates else primary.get("background_style", {}),
            "layout_type": cls._merge_string_vote([item.get("layout_type") for item in page_results]) or primary.get("layout_type", fallback.get("layout_type", "template")),
            "visual_mood": cls._merge_string_vote([item.get("visual_mood") for item in page_results]) or primary.get("visual_mood", ""),
            "design_style": cls._merge_string_vote([item.get("design_style") for item in page_results]) or primary.get("design_style", ""),
            "composition_style": cls._merge_string_vote([item.get("composition_style") for item in page_results]) or primary.get("composition_style", ""),
            "typography_dna": {
                **(primary.get("typography_dna") if isinstance(primary.get("typography_dna"), dict) else {}),
                **cls._merge_mapping_vote(
                    typography_candidates,
                    keys=["heading_style", "weight_hierarchy", "text_alignment", "dominant_case", "emphasis_pattern"],
                ),
            },
            "component_motifs": component_motifs or primary.get("component_motifs", {}),
            "infographic_elements": {
                **(primary.get("infographic_elements") if isinstance(primary.get("infographic_elements"), dict) else {}),
                **cls._merge_mapping_vote(infographic_candidates, keys=["graphs", "icons", "data_density"]),
            },
            "logo_anchor": cls._merge_string_vote([item.get("logo_anchor") for item in page_results]) or primary.get("logo_anchor", ""),
            "visual_hierarchy": {
                **(primary.get("visual_hierarchy") if isinstance(primary.get("visual_hierarchy"), dict) else {}),
                **cls._merge_mapping_vote(hierarchy_candidates, keys=["focal_role", "reading_order", "density", "whitespace", "emphasis"]),
            },
            "content_structure": {
                **(primary.get("content_structure") if isinstance(primary.get("content_structure"), dict) else {}),
                **cls._merge_mapping_vote(content_structure_candidates, keys=["headline_present", "support_present", "proof_modules", "legal_footer_present", "cta_prominence", "storytelling"]),
            },
            "image_treatment": {
                **(primary.get("image_treatment") if isinstance(primary.get("image_treatment"), dict) else {}),
                **cls._merge_mapping_vote(image_treatment_candidates, keys=["style", "crop", "subject_focus"]),
            },
            "brand_cues": {
                **(primary.get("brand_cues") if isinstance(primary.get("brand_cues"), dict) else {}),
                **cls._merge_mapping_vote(brand_cue_candidates, keys=["tone_keywords", "trust_markers", "recurring_shapes", "logo_lockup"]),
            },
            "composition_logic": {
                **(primary.get("composition_logic") if isinstance(primary.get("composition_logic"), dict) else {}),
                **cls._merge_mapping_vote(
                    composition_logic_candidates,
                    keys=["balance", "framing", "layering", "motion_flow", "focal_path"],
                ),
            },
            "visual_craft_dna": {
                **(primary.get("visual_craft_dna") if isinstance(primary.get("visual_craft_dna"), dict) else {}),
                **cls._merge_mapping_vote(
                    visual_craft_candidates,
                    keys=["depth_style", "rendering_style", "lighting", "polish_level", "material_cues", "dimensionality_cues"],
                ),
            },
            "subject_semantics": {
                **(primary.get("subject_semantics") if isinstance(primary.get("subject_semantics"), dict) else {}),
                **cls._merge_mapping_vote(
                    subject_semantic_candidates,
                    keys=["scene_type", "primary_subjects", "domain_cues", "financial_objects", "human_presence", "environment", "abstraction_level"],
                ),
            },
            "page_analysis_summary": page_summaries,
            "analysis_confidence": round(len(page_results) / max(len(selected), 1), 4),
        }
        return merged

    def extract_layout_dna(
        self,
        image_path: str,
        canvas_width: int | None = None,
        canvas_height: int | None = None,
        base_analysis: dict[str, Any] | None = None,
    ) -> dict:
        """Extract precise layout DNA from reference image with exact positions"""
        if canvas_width is None or canvas_height is None:
            try:
                with Path(image_path).open("rb"):
                    pass
                from PIL import Image

                with Image.open(image_path) as img:
                    detected_width, detected_height = img.size
            except Exception:  # noqa: BLE001
                detected_width, detected_height = 1080, 1080
            canvas_width = canvas_width or detected_width
            canvas_height = canvas_height or detected_height

        # Use existing vision analysis to get editable zones
        if not isinstance(base_analysis, dict):
            base_analysis = self.analyze(
                image_path,
                {
                    "background_style": {"type": "flat", "dominant_mode": "flat", "source": "fallback"},
                    "layout_type": "template",
                    "editable_zones": [],
                },
            )

        editable_zones = base_analysis.get("editable_zones", [])

        # Build layout DNA with normalized + pixel positions
        layout_dna = {
            "canvas_size": {"width": canvas_width, "height": canvas_height},
            "zones": {},
            "zone_instances": [],
        }

        for index, zone in enumerate(editable_zones, start=1):
            role = zone.get("role")
            if not role:
                continue

            x = zone.get("x", 0)
            y = zone.get("y", 0)
            w = zone.get("w", 1)
            h = zone.get("h", 0.1)

            # Store both normalized and pixel values
            zone_payload = {
                "role": role,
                "instance_index": index,
                "normalized": {"x": x, "y": y, "w": w, "h": h},
                "pixels": {
                    "x": int(x * canvas_width),
                    "y": int(y * canvas_height),
                    "width": int(w * canvas_width),
                    "height": int(h * canvas_height)
                },
                "alignment": "center" if x < 0.3 and w > 0.4 else "left"
            }
            existing = layout_dna["zones"].get(role)
            if existing is None:
                layout_dna["zones"][role] = zone_payload
            elif isinstance(existing, list):
                existing.append(zone_payload)
            else:
                layout_dna["zones"][role] = [existing, zone_payload]
            layout_dna["zone_instances"].append(zone_payload)

        # Calculate spacing between elements
        layout_dna["spacing"] = self._analyze_spacing(editable_zones, canvas_height)

        return layout_dna

    @staticmethod
    def _analyze_spacing(zones: list[dict], canvas_h: int) -> dict:
        """Analyze vertical spacing between zones"""
        if not zones:
            return {"inter_element_gap": 20, "detected_gaps": []}

        sorted_zones = sorted(zones, key=lambda z: z.get("y", 0))

        gaps = []
        for i in range(len(sorted_zones) - 1):
            current_y = sorted_zones[i].get("y", 0)
            current_h = sorted_zones[i].get("h", 0)
            next_y = sorted_zones[i + 1].get("y", 0)

            gap = next_y - (current_y + current_h)
            if gap > 0:
                gaps.append(int(gap * canvas_h))

        avg_gap = int(sum(gaps) / len(gaps)) if gaps else 20

        return {
            "inter_element_gap": avg_gap,
            "detected_gaps": gaps
        }
