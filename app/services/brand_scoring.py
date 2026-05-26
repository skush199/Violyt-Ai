from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from statistics import mean
from typing import Any

from app.ai.rag.ocr import OCRService
from app.ai.tone_intelligence import ToneIntelligenceService
from app.core.config import get_settings
from app.integrations.object_storage import LocalObjectStorage
from PIL import Image

logger = logging.getLogger(__name__)


class BrandScoringService:
    DIRNAME = "brand_scoring"
    WEIGHTING = {
        "on_brand": 0.4,
        "prompt_adherence": 0.35,
        "relevance": 0.25,
    }
    TOPIC_STOPWORDS = {
        "a",
        "an",
        "and",
        "about",
        "against",
        "brand",
        "campaign",
        "check",
        "consistency",
        "content",
        "create",
        "creative",
        "design",
        "engaging",
        "evaluate",
        "file",
        "for",
        "format",
        "generate",
        "guideline",
        "guidelines",
        "goal",
        "image",
        "instagram",
        "layout",
        "media",
        "new",
        "panel",
        "platform",
        "png",
        "post",
        "prompt",
        "review",
        "score",
        "share",
        "social",
        "static",
        "strategy",
        "that",
        "the",
        "tone",
        "using",
        "visual",
        "with",
    }

    def __init__(self, session) -> None:
        self.session = session
        self.storage = LocalObjectStorage()
        self.ocr = OCRService()
        self.tone = ToneIntelligenceService()
        self.base_dir = Path(get_settings().object_storage_base_path) / self.DIRNAME
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def build_scorecard(
        self,
        *,
        prompt: str,
        studio_panel: dict[str, Any],
        generated_payload: dict[str, Any],
        brand_context: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        explainability: dict[str, Any],
        output_assets: list[dict[str, Any]],
        reference_assets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        copy_text = self._copy_text(generated_payload)
        tone_feedback = self.tone._heuristic_evaluate(
            copy_text,
            brand_context,
            persona_context,
            content_payload=generated_payload,
            message_strategy=(
                explainability.get("message_strategy")
                if isinstance(explainability.get("message_strategy"), dict)
                else {}
            ),
            objective_context=objective_context,
        )
        visual_review = self._visual_review_for_assets(
            output_assets=output_assets,
            prompt=prompt,
            brand_context=brand_context,
            reference_assets=reference_assets,
        )
        combined_output_text = " ".join(
            part
            for part in [
                copy_text,
                self._visual_text_excerpt(visual_review),
            ]
            if str(part or "").strip()
        ).strip()

        on_brand = self._on_brand_score(
            tone_feedback=tone_feedback,
            visual_review=visual_review,
            explainability=explainability,
        )
        prompt_adherence = self._prompt_adherence_score(
            prompt=prompt,
            combined_output_text=combined_output_text,
            studio_panel=studio_panel,
            visual_review=visual_review,
            output_assets=output_assets,
        )
        relevance = self._relevance_score(
            prompt=prompt,
            combined_output_text=combined_output_text,
            tone_feedback=tone_feedback,
            persona_context=persona_context,
            objective_context=objective_context,
            brand_context=brand_context,
            visual_review=visual_review,
        )
        overall_score = max(
            0,
            min(
                100,
                int(
                    round(
                        (on_brand * self.WEIGHTING["on_brand"])
                        + (prompt_adherence * self.WEIGHTING["prompt_adherence"])
                        + (relevance * self.WEIGHTING["relevance"])
                    )
                ),
            ),
        )
        return {
            "overall_score": overall_score,
            "score_breakdown": {
                "on_brand": on_brand,
                "prompt_adherence": prompt_adherence,
                "relevance": relevance,
            },
            "weighting": dict(self.WEIGHTING),
            "summary": [
                self._on_brand_summary(on_brand),
                self._prompt_adherence_summary(prompt_adherence),
                self._relevance_summary(relevance),
            ],
        }

    def save_scorecard(
        self,
        *,
        output_id: str,
        scorecard: dict[str, Any],
    ) -> str:
        file_path = self.base_dir / f"{output_id}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(scorecard, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(file_path)

    def _visual_review_for_assets(
        self,
        *,
        output_assets: list[dict[str, Any]],
        prompt: str,
        brand_context: dict[str, Any],
        reference_assets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        blocks: list[dict[str, Any]] = []
        reference_style_profile = self._reference_style_profile(reference_assets or [])

        for index, asset in enumerate(output_assets, start=1):
            storage_path = str(asset.get("storage_path") or "").strip()
            mime_type = str(asset.get("mime_type") or "").strip()
            asset_kind = str(asset.get("asset_kind") or "").strip().lower() or "image"
            if not storage_path or asset_kind not in {"image", "document", "presentation"}:
                continue
            if not self.storage.exists(storage_path):
                continue
            absolute_path = self.storage.absolute_path(storage_path)
            try:
                extracted = self.ocr.extract(absolute_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("brand_scoring.ocr_failed storage_path=%s error=%s", storage_path, exc)
                continue
            ocr_text = str(extracted.get("text") or "").strip()
            page_images = [str(path).strip() for path in (extracted.get("images") or []) if str(path).strip()]
            if not page_images and asset_kind == "image":
                page_images = [absolute_path]
            page_reviews: list[dict[str, Any]] = []
            for page_index, image_path in enumerate(page_images or [absolute_path], start=1):
                page_text = ocr_text if len(page_images) <= 1 else ""
                if len(page_images) > 1:
                    try:
                        page_extracted = self.ocr.extract(image_path)
                    except Exception:  # noqa: BLE001
                        page_extracted = {}
                    page_text = str(page_extracted.get("text") or "").strip()
                    analysis = self._read_visual_analysis_path(
                        str(page_extracted.get("analysis_path") or "").strip()
                    )
                else:
                    analysis = self._read_visual_analysis_path(
                        str(extracted.get("analysis_path") or "").strip()
                    )
                    if not analysis:
                        analysis = self._read_visual_analysis_for_image_path(image_path)
                page_reviews.append(
                    self._build_visual_page_review(
                        page_index=page_index,
                        image_path=image_path,
                        analysis=analysis,
                        expected_prompt=prompt,
                        page_text=page_text,
                        brand_context=brand_context,
                        reference_style_profile=reference_style_profile,
                    )
                )
            prompt_alignment_score = self._average_visual_metric(page_reviews, "prompt_alignment_score")
            layout_readability_score = self._average_visual_metric(page_reviews, "layout_readability_score")
            density_score = self._average_visual_metric(page_reviews, "density_score")
            brand_alignment_score = self._average_visual_metric(page_reviews, "brand_alignment_score")
            style_alignment_score = self._average_visual_metric(page_reviews, "style_alignment_score")
            mood_alignment_score = self._average_visual_metric(page_reviews, "mood_alignment_score")
            typography_alignment_score = self._average_visual_metric(page_reviews, "typography_alignment_score")
            motif_alignment_score = self._average_visual_metric(page_reviews, "motif_alignment_score")
            reference_similarity_score = self._average_visual_metric(page_reviews, "reference_similarity_score")
            hierarchy_score = self._average_visual_metric(page_reviews, "hierarchy_score")
            crowding_score = self._average_visual_metric(page_reviews, "crowding_score")
            page_balance_score = self._average_visual_metric(page_reviews, "page_balance_score")
            ocr_confidence_score = self._average_visual_metric(page_reviews, "ocr_confidence_score")
            visual_diagnostic_score = int(
                round(
                    mean(
                        [
                            prompt_alignment_score,
                            layout_readability_score,
                            density_score,
                            brand_alignment_score,
                            style_alignment_score,
                            mood_alignment_score,
                            typography_alignment_score,
                            motif_alignment_score,
                            reference_similarity_score,
                            hierarchy_score,
                            crowding_score,
                            page_balance_score,
                            ocr_confidence_score,
                        ]
                    )
                )
            )
            blocks.append(
                {
                    "asset_id": asset.get("asset_id") or f"asset-{index}",
                    "asset_name": str((asset.get("metadata") or {}).get("label") or Path(storage_path).stem or f"asset-{index}"),
                    "visual_review": {
                        "page_reviews": page_reviews,
                        "findings": self._visual_findings_from_pages(page_reviews, expected_prompt=prompt),
                        "document_segments": self._document_segments_from_page_reviews(page_reviews, asset_kind=asset_kind),
                        "region_overview": self._region_overview_from_pages(page_reviews),
                        "diagnostics": {
                            "prompt_alignment_score": prompt_alignment_score,
                            "layout_readability_score": layout_readability_score,
                            "density_score": density_score,
                            "brand_alignment_score": brand_alignment_score,
                            "style_alignment_score": style_alignment_score,
                            "mood_alignment_score": mood_alignment_score,
                            "typography_alignment_score": typography_alignment_score,
                            "motif_alignment_score": motif_alignment_score,
                            "reference_similarity_score": reference_similarity_score,
                            "hierarchy_score": hierarchy_score,
                            "crowding_score": crowding_score,
                            "page_balance_score": page_balance_score,
                            "ocr_confidence_score": ocr_confidence_score,
                            "visual_diagnostic_score": visual_diagnostic_score,
                        },
                        "ocr_text": ocr_text[:4000],
                    },
                    "mime_type": mime_type,
                    "storage_path": storage_path,
                    "asset_kind": asset_kind,
                }
            )
        if not blocks:
            return {
                "asset_count": 0,
                "page_count": 0,
                "prompt_alignment_score": 70,
                "layout_readability_score": 70,
                "density_score": 70,
                "brand_alignment_score": 70,
                "style_alignment_score": 70,
                "mood_alignment_score": 70,
                "typography_alignment_score": 70,
                "motif_alignment_score": 70,
                "reference_similarity_score": 70,
                "aesthetic_consistency_score": 70,
                "hierarchy_score": 70,
                "crowding_score": 70,
                "page_balance_score": 70,
                "ocr_confidence_score": 70,
                "visual_diagnostic_score": 70,
                "findings": [],
                "page_reviews": [],
                "document_segments": [],
                "region_overview": {},
            }
        return self._visual_review_report(blocks)

    @staticmethod
    def _copy_text(generated_payload: dict[str, Any]) -> str:
        snippets: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, str):
                text = value.strip()
                if text:
                    snippets.append(text)
                return
            if isinstance(value, dict):
                for key, nested in value.items():
                    if str(key).strip().lower() in {"storage_path", "asset_url", "mime_type", "font_family"}:
                        continue
                    visit(nested)
                return
            if isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(generated_payload or {})
        seen: set[str] = set()
        ordered: list[str] = []
        for snippet in snippets:
            normalized = snippet.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(snippet)
        return " ".join(ordered[:40]).strip()

    @staticmethod
    def _visual_text_excerpt(visual_review: dict[str, Any]) -> str:
        excerpts: list[str] = []
        for page in visual_review.get("page_reviews") or []:
            if not isinstance(page, dict):
                continue
            text = str(page.get("ocr_text_excerpt") or "").strip()
            if text:
                excerpts.append(text)
        return " ".join(excerpts[:6]).strip()

    @staticmethod
    def _source_usage_score(explainability: dict[str, Any]) -> int:
        input_access_summary = (
            explainability.get("input_access_summary")
            if isinstance(explainability.get("input_access_summary"), dict)
            else {}
        )
        weighted_scores: list[tuple[float, float]] = []
        for source_name, weight in (
            ("brand_context", 0.7),
            ("persona_context", 0.2),
            ("objective_context", 0.1),
        ):
            summary = input_access_summary.get(source_name)
            if not isinstance(summary, dict):
                continue
            used = len(summary.get("used_paths") or [])
            unused = len(summary.get("unused_paths") or [])
            total = used + unused
            if total <= 0:
                continue
            weighted_scores.append((((used / total) * 100.0), weight))
        if not weighted_scores:
            return 65
        total_weight = sum(weight for _, weight in weighted_scores) or 1.0
        score = sum(score * (weight / total_weight) for score, weight in weighted_scores)
        return max(0, min(100, int(round(score))))

    def _on_brand_score(
        self,
        *,
        tone_feedback: dict[str, Any],
        visual_review: dict[str, Any],
        explainability: dict[str, Any],
    ) -> int:
        dimensions = tone_feedback.get("persuasion_dimensions") if isinstance(tone_feedback.get("persuasion_dimensions"), dict) else {}
        text_brand = float(dimensions.get("brand_alignment") or 0.0)
        visual_brand = (
            (float(visual_review.get("brand_alignment_score") or text_brand or 70.0) * 0.85)
            + (float(visual_review.get("aesthetic_consistency_score") or 70.0) * 0.15)
        )
        usage_score = float(self._source_usage_score(explainability))
        score = (
            (visual_brand * 0.5)
            + (text_brand * 0.35)
            + (usage_score * 0.15)
        )
        if visual_brand < 55:
            score -= 8.0
        if usage_score < 25:
            score = min(score, 74.0)
        return max(0, min(100, int(round(score))))

    def _prompt_adherence_score(
        self,
        *,
        prompt: str,
        combined_output_text: str,
        studio_panel: dict[str, Any],
        visual_review: dict[str, Any],
        output_assets: list[dict[str, Any]],
    ) -> int:
        text_prompt = float(self._prompt_alignment_score(prompt, combined_output_text, []))
        visual_prompt = float(visual_review.get("prompt_alignment_score") or text_prompt or 70.0)
        format_score = float(
            self._format_fit_score(
                studio_panel=studio_panel,
                visual_review=visual_review,
                output_assets=output_assets,
            )
        )
        score = (visual_prompt * 0.5) + (text_prompt * 0.35) + (format_score * 0.15)
        if visual_prompt < 50 and text_prompt < 50:
            score -= 10.0
        return max(0, min(100, int(round(score))))

    def _relevance_score(
        self,
        *,
        prompt: str,
        combined_output_text: str,
        tone_feedback: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        brand_context: dict[str, Any],
        visual_review: dict[str, Any],
    ) -> int:
        context_reference = self._context_reference_text(
            persona_context=persona_context,
            objective_context=objective_context,
            brand_context=brand_context,
        )
        if context_reference:
            context_score = float(self._prompt_alignment_score(context_reference, combined_output_text, []))
        else:
            context_score = 70.0
        dimensions = tone_feedback.get("persuasion_dimensions") if isinstance(tone_feedback.get("persuasion_dimensions"), dict) else {}
        quality_score = mean(
            [
                float(dimensions.get("clarity") or 0.0),
                float(dimensions.get("proof_strength") or 0.0),
                float(dimensions.get("objection_handling") or 0.0),
                float(dimensions.get("distinctiveness") or 0.0),
            ]
        )
        prompt_support = float(self._prompt_alignment_score(prompt, combined_output_text, []))
        visual_quality = mean(
            [
                float(visual_review.get("layout_readability_score") or 70.0),
                float(visual_review.get("visual_diagnostic_score") or 70.0),
            ]
        )
        score = (
            (context_score * 0.45)
            + (quality_score * 0.3)
            + (prompt_support * 0.15)
            + (visual_quality * 0.10)
        )
        if float(dimensions.get("distinctiveness") or 0.0) < 55:
            score -= 6.0
        return max(0, min(100, int(round(score))))

    @staticmethod
    def _context_reference_text(
        *,
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        brand_context: dict[str, Any],
    ) -> str:
        parts: list[str] = []

        def extend_from(value: Any) -> None:
            if isinstance(value, str):
                text = value.strip()
                if text:
                    parts.append(text)
                return
            if isinstance(value, dict):
                for key, nested in value.items():
                    if str(key).strip().lower() in {"id", "asset_id", "storage_path"}:
                        continue
                    extend_from(nested)
                return
            if isinstance(value, list):
                for nested in value:
                    extend_from(nested)

        extend_from(persona_context)
        extend_from(objective_context)
        audience = brand_context.get("audience_insights") if isinstance(brand_context.get("audience_insights"), dict) else {}
        extend_from(audience)
        seen: set[str] = set()
        ordered: list[str] = []
        for part in parts:
            normalized = part.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(part)
        return " ".join(ordered[:30]).strip()

    @staticmethod
    def _format_fit_score(
        *,
        studio_panel: dict[str, Any],
        visual_review: dict[str, Any],
        output_assets: list[dict[str, Any]],
    ) -> int:
        format_name = str(studio_panel.get("format") or "").strip().lower()
        page_count = int(visual_review.get("page_count") or 0)
        asset_count = len(output_assets)
        if format_name == "carousel":
            if page_count >= 3 or asset_count >= 3:
                return 100
            if page_count >= 2 or asset_count >= 2:
                return 82
            return 45
        if format_name == "infographic":
            if page_count >= 1 or asset_count >= 1:
                return 100
            return 50
        if format_name == "static":
            if page_count >= 1 or asset_count >= 1:
                return 100
            return 55
        if page_count >= 1 or asset_count >= 1:
            return 90
        return 60

    @staticmethod
    def _on_brand_summary(score: int) -> str:
        if score >= 85:
            return "Strong visual brand fit."
        if score >= 70:
            return "Output is mostly on-brand with minor drift."
        return "Brand fit is inconsistent and needs correction."

    @staticmethod
    def _prompt_adherence_summary(score: int) -> str:
        if score >= 85:
            return "Prompt topic and format are followed closely."
        if score >= 70:
            return "Prompt intent is mostly followed with some gaps."
        return "Prompt adherence is weak and the output misses key intent."

    @staticmethod
    def _relevance_summary(score: int) -> str:
        if score >= 85:
            return "Output is highly relevant to the audience and objective."
        if score >= 70:
            return "Output is relevant but slightly generic."
        return "Output relevance is weak for the audience or objective."

    @classmethod
    def _prompt_topic_tokens(cls, prompt: str, *, limit: int = 12) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", str(prompt or "").lower()):
            if token in cls.TOPIC_STOPWORDS or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= limit:
                break
        return tokens

    @staticmethod
    def _extract_brand_name_tokens(brand_context: dict[str, Any]) -> list[str]:
        tokens: list[str] = []
        for candidate in (
            brand_context.get("brand_name"),
            (brand_context.get("identity") or {}).get("brand_name") if isinstance(brand_context.get("identity"), dict) else None,
            (brand_context.get("identity") or {}).get("name") if isinstance(brand_context.get("identity"), dict) else None,
        ):
            for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", str(candidate or "").lower()):
                if token not in tokens:
                    tokens.append(token)
        return tokens

    @staticmethod
    def _extract_brand_palette_hexes(brand_context: dict[str, Any]) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    if key in {"hex", "hex_code"}:
                        hex_code = str(nested or "").strip().upper()
                        if hex_code and not hex_code.startswith("#") and re.fullmatch(r"[0-9A-F]{6}", hex_code):
                            hex_code = f"#{hex_code}"
                        if re.fullmatch(r"#[0-9A-F]{6}", hex_code) and hex_code not in seen:
                            seen.add(hex_code)
                            results.append(hex_code)
                    else:
                        visit(nested)
                return
            if isinstance(value, list):
                for nested in value:
                    visit(nested)
                return
            if isinstance(value, str):
                for match in re.findall(r"#[0-9A-Fa-f]{6}", value):
                    hex_code = match.upper()
                    if hex_code not in seen:
                        seen.add(hex_code)
                        results.append(hex_code)

        visit(brand_context)
        return results

    @classmethod
    def _normalized_signal(cls, value: Any) -> str:
        return " ".join(re.findall(r"[A-Za-z0-9]+", str(value or "").strip().lower()))

    @classmethod
    def _normalized_signal_list(cls, values: Any, *, limit: int = 12) -> list[str]:
        items: list[str] = []

        def visit(value: Any) -> None:
            if len(items) >= limit:
                return
            if isinstance(value, str):
                normalized = cls._normalized_signal(value)
                if normalized and normalized not in items:
                    items.append(normalized)
                return
            if isinstance(value, dict):
                for nested in value.values():
                    visit(nested)
                    if len(items) >= limit:
                        break
                return
            if isinstance(value, list):
                for nested in value:
                    visit(nested)
                    if len(items) >= limit:
                        break

        visit(values)
        return items[:limit]

    @classmethod
    def _string_alignment_score(cls, observed: Any, expected_values: list[str]) -> int:
        expected = [item for item in (cls._normalized_signal_list(expected_values, limit=12)) if item]
        if not expected:
            return 70
        observed_normalized = cls._normalized_signal(observed)
        if not observed_normalized:
            return 50
        observed_tokens = set(observed_normalized.split())
        best = 35
        for candidate in expected:
            candidate_tokens = set(candidate.split())
            if observed_normalized == candidate:
                return 100
            overlap = len(observed_tokens & candidate_tokens)
            if not overlap:
                continue
            coverage = overlap / max(len(candidate_tokens), 1)
            precision = overlap / max(len(observed_tokens), 1)
            score = int(round(45 + ((coverage * 0.65) + (precision * 0.35)) * 55))
            best = max(best, min(score, 96))
        return best

    @classmethod
    def _set_alignment_score(cls, observed_values: set[str], expected_values: set[str]) -> int:
        if not expected_values:
            return 70
        if not observed_values:
            return 50
        overlap = len(observed_values & expected_values)
        if overlap <= 0:
            return 35
        recall = overlap / max(len(expected_values), 1)
        precision = overlap / max(len(observed_values), 1)
        return max(0, min(100, int(round(35 + ((recall * 0.65) + (precision * 0.35)) * 65))))

    @classmethod
    def _expected_visual_identity(cls, brand_context: dict[str, Any]) -> dict[str, Any]:
        visual_identity = brand_context.get("visual_identity") if isinstance(brand_context.get("visual_identity"), dict) else {}
        voice_tone = brand_context.get("voice_tone") if isinstance(brand_context.get("voice_tone"), dict) else {}
        typography_preferences = (
            visual_identity.get("typography_preferences")
            if isinstance(visual_identity.get("typography_preferences"), dict)
            else {}
        )
        typography = visual_identity.get("typography") if isinstance(visual_identity.get("typography"), dict) else {}
        composition_logic = (
            visual_identity.get("composition_logic")
            if isinstance(visual_identity.get("composition_logic"), dict)
            else {}
        )
        component_motifs = (
            visual_identity.get("component_motifs")
            if isinstance(visual_identity.get("component_motifs"), dict)
            else {}
        )
        font_families = [
            cls._normalized_signal(item.get("name"))
            for item in (typography.get("font_families") or [])
            if isinstance(item, dict) and cls._normalized_signal(item.get("name"))
        ]
        motif_keys = {
            cls._normalized_signal(str(key).replace("_", " "))
            for key, value in component_motifs.items()
            if value and cls._normalized_signal(str(key).replace("_", " "))
        }
        return {
            "design_styles": cls._normalized_signal_list(
                [
                    visual_identity.get("design_style"),
                    *(visual_identity.get("design_styles") or []),
                    *(visual_identity.get("style_summary") or [] if isinstance(visual_identity.get("style_summary"), list) else [visual_identity.get("style_summary")]),
                ],
                limit=8,
            ),
            "visual_moods": cls._normalized_signal_list(
                [
                    visual_identity.get("brand_mood"),
                    *(visual_identity.get("visual_moods") or []),
                    voice_tone.get("primary_emotion"),
                    voice_tone.get("secondary_emotion"),
                ],
                limit=8,
            ),
            "composition_styles": cls._normalized_signal_list(
                [
                    visual_identity.get("composition_style"),
                    *(composition_logic.get("balances") or []),
                    *(composition_logic.get("framings") or []),
                    *(composition_logic.get("layerings") or []),
                ],
                limit=8,
            ),
            "heading_styles": cls._normalized_signal_list(typography_preferences.get("heading_styles") or [], limit=8),
            "text_alignments": cls._normalized_signal_list(typography_preferences.get("text_alignments") or [], limit=6),
            "dominant_cases": cls._normalized_signal_list(typography_preferences.get("dominant_cases") or [], limit=6),
            "emphasis_patterns": cls._normalized_signal_list(typography_preferences.get("emphasis_patterns") or [], limit=6),
            "font_families": font_families[:6],
            "motif_keys": motif_keys,
        }

    @classmethod
    def _reference_style_profile(cls, reference_assets: list[dict[str, Any]]) -> dict[str, Any]:
        design_styles: list[str] = []
        visual_moods: list[str] = []
        composition_styles: list[str] = []
        heading_styles: list[str] = []
        text_alignments: list[str] = []
        dominant_cases: list[str] = []
        emphasis_patterns: list[str] = []
        font_families: list[str] = []
        motif_keys: set[str] = set()

        for asset in reference_assets:
            if not isinstance(asset, dict):
                continue
            style = asset.get("style_characteristics") if isinstance(asset.get("style_characteristics"), dict) else {}
            typography_dna = style.get("typography_dna") if isinstance(style.get("typography_dna"), dict) else {}
            component_motifs = style.get("component_motifs") if isinstance(style.get("component_motifs"), dict) else {}
            font_candidates = style.get("font_families") if isinstance(style.get("font_families"), list) else []
            design_styles.extend(cls._normalized_signal_list([style.get("design_style"), asset.get("design_style")], limit=4))
            visual_moods.extend(cls._normalized_signal_list([style.get("visual_mood"), asset.get("visual_mood")], limit=4))
            composition_styles.extend(cls._normalized_signal_list([style.get("composition_style"), style.get("layout_type")], limit=4))
            heading_styles.extend(cls._normalized_signal_list([typography_dna.get("heading_style")], limit=2))
            text_alignments.extend(cls._normalized_signal_list([typography_dna.get("text_alignment")], limit=2))
            dominant_cases.extend(cls._normalized_signal_list([typography_dna.get("dominant_case")], limit=2))
            emphasis_patterns.extend(cls._normalized_signal_list([typography_dna.get("emphasis_pattern")], limit=2))
            for item in font_candidates:
                if isinstance(item, dict):
                    normalized = cls._normalized_signal(item.get("name"))
                    if normalized and normalized not in font_families:
                        font_families.append(normalized)
            motif_keys.update(
                cls._normalized_signal(str(key).replace("_", " "))
                for key, value in component_motifs.items()
                if value and cls._normalized_signal(str(key).replace("_", " "))
            )

        return {
            "design_styles": design_styles[:8],
            "visual_moods": visual_moods[:8],
            "composition_styles": composition_styles[:8],
            "heading_styles": heading_styles[:8],
            "text_alignments": text_alignments[:6],
            "dominant_cases": dominant_cases[:6],
            "emphasis_patterns": emphasis_patterns[:6],
            "font_families": font_families[:6],
            "motif_keys": motif_keys,
        }

    @classmethod
    def _style_alignment_score(
        cls,
        *,
        brand_context: dict[str, Any],
        design_style: str,
        composition_style: str,
    ) -> int:
        expected = cls._expected_visual_identity(brand_context)
        scores = []
        if expected["design_styles"]:
            scores.append(cls._string_alignment_score(design_style, expected["design_styles"]))
        if expected["composition_styles"]:
            scores.append(cls._string_alignment_score(composition_style, expected["composition_styles"]))
        if not scores:
            return 70
        return int(round(mean(scores)))

    @classmethod
    def _mood_alignment_score(cls, *, brand_context: dict[str, Any], visual_mood: str) -> int:
        expected = cls._expected_visual_identity(brand_context)
        if not expected["visual_moods"]:
            return 70
        return cls._string_alignment_score(visual_mood, expected["visual_moods"])

    @classmethod
    def _typography_alignment_score(
        cls,
        *,
        brand_context: dict[str, Any],
        typography_dna: dict[str, Any],
        font_families: list[str],
    ) -> int:
        expected = cls._expected_visual_identity(brand_context)
        scores = []
        if expected["heading_styles"]:
            scores.append(cls._string_alignment_score(typography_dna.get("heading_style"), expected["heading_styles"]))
        if expected["text_alignments"]:
            scores.append(cls._string_alignment_score(typography_dna.get("text_alignment"), expected["text_alignments"]))
        if expected["dominant_cases"]:
            scores.append(cls._string_alignment_score(typography_dna.get("dominant_case"), expected["dominant_cases"]))
        if expected["emphasis_patterns"]:
            scores.append(cls._string_alignment_score(typography_dna.get("emphasis_pattern"), expected["emphasis_patterns"]))
        if expected["font_families"]:
            observed_fonts = {
                cls._normalized_signal(item)
                for item in font_families
                if cls._normalized_signal(item)
            }
            scores.append(cls._set_alignment_score(observed_fonts, set(expected["font_families"])))
        if not scores:
            return 70
        return int(round(mean(scores)))

    @classmethod
    def _motif_alignment_score(
        cls,
        *,
        brand_context: dict[str, Any],
        component_motifs: dict[str, Any],
    ) -> int:
        expected = cls._expected_visual_identity(brand_context)
        observed = {
            cls._normalized_signal(str(key).replace("_", " "))
            for key, value in component_motifs.items()
            if value and cls._normalized_signal(str(key).replace("_", " "))
        }
        return cls._set_alignment_score(observed, set(expected["motif_keys"]))

    @classmethod
    def _reference_similarity_score(
        cls,
        *,
        reference_style_profile: dict[str, Any],
        design_style: str,
        visual_mood: str,
        composition_style: str,
        typography_dna: dict[str, Any],
        component_motifs: dict[str, Any],
        font_families: list[str],
    ) -> int:
        if not reference_style_profile:
            return 70
        scores = []
        if reference_style_profile.get("design_styles"):
            scores.append(cls._string_alignment_score(design_style, reference_style_profile.get("design_styles") or []))
        if reference_style_profile.get("visual_moods"):
            scores.append(cls._string_alignment_score(visual_mood, reference_style_profile.get("visual_moods") or []))
        if reference_style_profile.get("composition_styles"):
            scores.append(cls._string_alignment_score(composition_style, reference_style_profile.get("composition_styles") or []))
        if reference_style_profile.get("heading_styles"):
            scores.append(cls._string_alignment_score(typography_dna.get("heading_style"), reference_style_profile.get("heading_styles") or []))
        if reference_style_profile.get("text_alignments"):
            scores.append(cls._string_alignment_score(typography_dna.get("text_alignment"), reference_style_profile.get("text_alignments") or []))
        if reference_style_profile.get("dominant_cases"):
            scores.append(cls._string_alignment_score(typography_dna.get("dominant_case"), reference_style_profile.get("dominant_cases") or []))
        if reference_style_profile.get("emphasis_patterns"):
            scores.append(cls._string_alignment_score(typography_dna.get("emphasis_pattern"), reference_style_profile.get("emphasis_patterns") or []))
        reference_fonts = {
            cls._normalized_signal(item)
            for item in (reference_style_profile.get("font_families") or [])
            if cls._normalized_signal(item)
        }
        if reference_fonts:
            observed_fonts = {
                cls._normalized_signal(item)
                for item in font_families
                if cls._normalized_signal(item)
            }
            scores.append(cls._set_alignment_score(observed_fonts, reference_fonts))
        reference_motifs = {
            cls._normalized_signal(item)
            for item in (reference_style_profile.get("motif_keys") or set())
            if cls._normalized_signal(item)
        }
        if reference_motifs:
            observed_motifs = {
                cls._normalized_signal(str(key).replace("_", " "))
                for key, value in component_motifs.items()
                if value and cls._normalized_signal(str(key).replace("_", " "))
            }
            scores.append(cls._set_alignment_score(observed_motifs, reference_motifs))
        if not scores:
            return 70
        return int(round(mean(scores)))

    @staticmethod
    def _read_visual_analysis_path(analysis_path: str) -> dict[str, Any]:
        if not analysis_path:
            return {}
        path = Path(analysis_path)
        if not path.exists():
            return {}
        try:
            parsed = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _read_visual_analysis_for_image_path(self, image_path: str) -> dict[str, Any]:
        image = Path(image_path)
        direct = image.with_name(f"{image.stem}_analysis.json")
        analysis = self._read_visual_analysis_path(str(direct))
        if analysis:
            return analysis
        try:
            extracted = self.ocr.extract(image_path)
        except Exception:  # noqa: BLE001
            return {}
        return self._read_visual_analysis_path(str(extracted.get("analysis_path") or "").strip())

    @staticmethod
    def _image_canvas_size(image_path: str) -> tuple[int, int] | None:
        try:
            with Image.open(image_path) as image:
                return int(image.width or 0), int(image.height or 0)
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    def _prompt_term_diagnostics(cls, expected_prompt: str, observed_text: str, labels: list[str]) -> tuple[list[str], list[str]]:
        prompt_tokens = []
        for token in cls._prompt_topic_tokens(expected_prompt):
            if token not in prompt_tokens:
                prompt_tokens.append(token)
        observed_tokens = set(cls._prompt_topic_tokens(f"{observed_text} {' '.join(labels)}", limit=32))
        matched = [token for token in prompt_tokens if token in observed_tokens]
        missing = [token for token in prompt_tokens if token not in observed_tokens]
        return matched, missing

    @staticmethod
    def _layout_region_diagnostics(
        *,
        structured_text: list[dict[str, Any]],
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any]:
        if canvas_width <= 0 or canvas_height <= 0:
            return {
                "edge_crowding_count": 0,
                "overlap_count": 0,
                "text_coverage_ratio": 0.0,
                "vertical_distribution": {"top": 0, "middle": 0, "bottom": 0},
                "headline_prominence": 1.0,
            }
        boxes: list[tuple[int, int, int, int]] = []
        areas: list[int] = []
        distribution = {"top": 0, "middle": 0, "bottom": 0}
        edge_crowding_count = 0
        margin_x = canvas_width * 0.05
        margin_y = canvas_height * 0.05
        for entry in structured_text:
            bbox = entry.get("bounding_box") if isinstance(entry.get("bounding_box"), dict) else {}
            x = int(bbox.get("x", bbox.get("left", 0)) or 0)
            y = int(bbox.get("y", bbox.get("top", 0)) or 0)
            width = int(bbox.get("w", bbox.get("width", 0)) or 0)
            height = int(bbox.get("h", bbox.get("height", 0)) or 0)
            if width <= 0 or height <= 0:
                continue
            boxes.append((x, y, width, height))
            areas.append(width * height)
            center_y = y + (height / 2.0)
            if center_y < canvas_height / 3.0:
                distribution["top"] += 1
            elif center_y < (canvas_height * 2.0) / 3.0:
                distribution["middle"] += 1
            else:
                distribution["bottom"] += 1
            if x <= margin_x or y <= margin_y or (x + width) >= (canvas_width - margin_x) or (y + height) >= (canvas_height - margin_y):
                edge_crowding_count += 1
        overlap_count = 0
        for index, (ax, ay, aw, ah) in enumerate(boxes):
            for bx, by, bw, bh in boxes[index + 1:]:
                overlap_width = min(ax + aw, bx + bw) - max(ax, bx)
                overlap_height = min(ay + ah, by + bh) - max(ay, by)
                if overlap_width > 0 and overlap_height > 0:
                    overlap_count += 1
        total_area = sum(areas)
        coverage_ratio = total_area / max(float(canvas_width * canvas_height), 1.0)
        headline_prominence = 1.0
        if areas:
            sorted_areas = sorted(areas, reverse=True)
            baseline = float(sorted_areas[1] if len(sorted_areas) > 1 else sorted_areas[0] or 1)
            headline_prominence = max(float(sorted_areas[0]) / max(baseline, 1.0), 1.0)
        return {
            "edge_crowding_count": edge_crowding_count,
            "overlap_count": overlap_count,
            "text_coverage_ratio": coverage_ratio,
            "vertical_distribution": distribution,
            "headline_prominence": headline_prominence,
        }

    @staticmethod
    def _hierarchy_score(*, hierarchy_signal: float, headline_prominence: float) -> int:
        score = 100.0
        if hierarchy_signal < 1.2:
            score -= 26.0
        elif hierarchy_signal < 1.5:
            score -= 14.0
        if headline_prominence < 1.15:
            score -= 20.0
        elif headline_prominence < 1.35:
            score -= 10.0
        elif headline_prominence > 2.4:
            score -= 6.0
        return max(0, min(100, int(round(score))))

    @staticmethod
    def _crowding_score(*, text_box_count: int, edge_crowding_count: int, overlap_count: int, text_coverage_ratio: float) -> int:
        score = 100.0
        if text_box_count > 8:
            score -= min((text_box_count - 8) * 4.0, 18.0)
        score -= min(edge_crowding_count * 6.0, 24.0)
        score -= min(overlap_count * 8.0, 24.0)
        if text_coverage_ratio > 0.35:
            score -= min((text_coverage_ratio - 0.35) * 100.0, 26.0)
        elif text_coverage_ratio < 0.03 and text_box_count > 0:
            score -= 8.0
        return max(0, min(100, int(round(score))))

    @staticmethod
    def _page_balance_score(vertical_distribution: dict[str, int]) -> int:
        counts = [int(vertical_distribution.get(key) or 0) for key in ("top", "middle", "bottom")]
        total = sum(counts)
        if total <= 1:
            return 100
        mean_value = total / 3.0
        imbalance = sum(abs(count - mean_value) for count in counts) / max(total, 1)
        score = 100.0 - min(imbalance * 60.0, 30.0)
        if counts[1] == 0 and counts[0] > 0 and counts[2] > 0:
            score -= 8.0
        return max(0, min(100, int(round(score))))

    @staticmethod
    def _page_findings(
        *,
        prompt_alignment_score: int,
        layout_readability_score: int,
        density_score: int,
        hierarchy_score: int,
        crowding_score: int,
        page_balance_score: int,
        missing_prompt_terms: list[str],
    ) -> list[str]:
        findings: list[str] = []
        if prompt_alignment_score < 60 and missing_prompt_terms:
            findings.append(f"Important prompt themes seem underrepresented: {', '.join(missing_prompt_terms[:4])}.")
        if layout_readability_score < 60:
            findings.append("Text hierarchy or readability looks weak on this page.")
        if density_score < 60 or crowding_score < 60:
            findings.append("The page appears visually crowded or text-heavy.")
        if hierarchy_score < 60:
            findings.append("Headline prominence is weak relative to the rest of the page.")
        if page_balance_score < 60:
            findings.append("Text distribution across the page feels unbalanced.")
        return findings

    @classmethod
    def _prompt_alignment_score(cls, expected_prompt: str, observed_text: str, labels: list[str]) -> int:
        prompt_tokens = set(cls._prompt_topic_tokens(expected_prompt))
        if not prompt_tokens:
            return 100
        observed_tokens = set(cls._prompt_topic_tokens(f"{observed_text} {' '.join(labels)}", limit=24))
        overlap = len(prompt_tokens & observed_tokens)
        label_overlap_bonus = 1 if any(token in " ".join(labels).lower() for token in prompt_tokens) else 0
        score = ((overlap + label_overlap_bonus) / max(len(prompt_tokens), 1)) * 100.0
        return max(0, min(100, int(round(score))))

    @staticmethod
    def _layout_readability_score(*, word_count: int, line_count: int, text_box_count: int, hierarchy_signal: float) -> int:
        score = 100.0
        if word_count > 90:
            score -= min((word_count - 90) * 0.7, 35.0)
        if line_count > 8:
            score -= min((line_count - 8) * 4.0, 20.0)
        if text_box_count > 10:
            score -= min((text_box_count - 10) * 3.0, 20.0)
        if hierarchy_signal < 1.2:
            score -= 18.0
        elif hierarchy_signal < 1.6:
            score -= 10.0
        elif hierarchy_signal >= 2.0:
            score += 4.0
        return max(0, min(100, int(round(score))))

    @staticmethod
    def _density_score(*, word_count: int, text_box_count: int, box_area: int) -> int:
        score = 100.0
        if word_count > 75:
            score -= min((word_count - 75) * 0.9, 40.0)
        if text_box_count > 9:
            score -= min((text_box_count - 9) * 4.0, 24.0)
        if box_area <= 0 and word_count > 0:
            score -= 10.0
        return max(0, min(100, int(round(score))))

    @classmethod
    def _brand_alignment_score(
        cls,
        *,
        brand_context: dict[str, Any],
        observed_text: str,
        labels: list[str],
        dominant_colors: list[str],
        style_alignment_score: int,
        mood_alignment_score: int,
        typography_alignment_score: int,
        motif_alignment_score: int,
        reference_similarity_score: int,
    ) -> int:
        base_score = 70.0
        brand_name_tokens = cls._extract_brand_name_tokens(brand_context)
        observed_tokens = set(cls._prompt_topic_tokens(f"{observed_text} {' '.join(labels)}", limit=24))
        if brand_name_tokens and observed_tokens.intersection(brand_name_tokens):
            base_score += 15.0
        palette_hexes = set(cls._extract_brand_palette_hexes(brand_context))
        observed_hexes = {
            hex_code if hex_code.startswith("#") else f"#{hex_code}"
            for hex_code in dominant_colors
            if hex_code
        }
        if palette_hexes and observed_hexes:
            overlap = len(palette_hexes & observed_hexes)
            if overlap:
                base_score += min(overlap * 7.0, 15.0)
            else:
                base_score -= 12.0
        score = (
            (base_score * 0.40)
            + (style_alignment_score * 0.15)
            + (mood_alignment_score * 0.10)
            + (typography_alignment_score * 0.10)
            + (motif_alignment_score * 0.10)
            + (reference_similarity_score * 0.15)
        )
        return max(0, min(100, int(round(score))))

    @classmethod
    def _categorical_consistency_score(cls, values: list[str]) -> int:
        normalized = [cls._normalized_signal(value) for value in values if cls._normalized_signal(value)]
        if not normalized:
            return 75
        if len(normalized) == 1:
            return 100
        counts: dict[str, int] = {}
        for value in normalized:
            counts[value] = counts.get(value, 0) + 1
        dominant_ratio = max(counts.values()) / max(len(normalized), 1)
        return max(0, min(100, int(round(35 + (dominant_ratio * 65)))))

    @classmethod
    def _motif_consistency_score(cls, motif_lists: list[set[str]]) -> int:
        normalized_sets = [item for item in motif_lists if item]
        if not normalized_sets:
            return 75
        if len(normalized_sets) == 1:
            return 100
        comparisons: list[float] = []
        for index, left in enumerate(normalized_sets):
            for right in normalized_sets[index + 1:]:
                union = left | right
                if not union:
                    continue
                comparisons.append(len(left & right) / len(union))
        if not comparisons:
            return 75
        return max(0, min(100, int(round(mean(comparisons) * 100.0))))

    @classmethod
    def _aesthetic_consistency_score(cls, page_reviews: list[dict[str, Any]]) -> int:
        if not page_reviews:
            return 75
        return int(
            round(
                mean(
                    [
                        cls._categorical_consistency_score([str(page.get("design_style") or "") for page in page_reviews]),
                        cls._categorical_consistency_score([str(page.get("visual_mood") or "") for page in page_reviews]),
                        cls._categorical_consistency_score(
                            [
                                str((page.get("typography_observed") or {}).get("text_alignment") or "")
                                for page in page_reviews
                                if isinstance(page.get("typography_observed"), dict)
                            ]
                        ),
                        cls._categorical_consistency_score(
                            [
                                str((page.get("typography_observed") or {}).get("dominant_case") or "")
                                for page in page_reviews
                                if isinstance(page.get("typography_observed"), dict)
                            ]
                        ),
                        cls._motif_consistency_score(
                            [
                                {
                                    cls._normalized_signal(item)
                                    for item in (page.get("motif_keys") or [])
                                    if cls._normalized_signal(item)
                                }
                                for page in page_reviews
                                if isinstance(page, dict)
                            ]
                        ),
                    ]
                )
            )
        )

    @staticmethod
    def _average_visual_metric(page_reviews: list[dict[str, Any]], field: str) -> int:
        values = [
            float(page.get(field) or 0.0)
            for page in page_reviews
            if isinstance(page, dict)
        ]
        if not values:
            return 0
        return max(0, min(100, int(round(sum(values) / len(values)))))

    @staticmethod
    def _visual_findings_from_pages(page_reviews: list[dict[str, Any]], *, expected_prompt: str) -> list[str]:
        findings: list[str] = []
        low_alignment = [page["page_index"] for page in page_reviews if int(page.get("prompt_alignment_score") or 0) < 50]
        if low_alignment:
            findings.append(
                f"Prompt/image consistency is weak on page(s) {', '.join(str(item) for item in low_alignment)} compared with the requested topic."
            )
        low_readability = [page["page_index"] for page in page_reviews if int(page.get("layout_readability_score") or 0) < 55]
        if low_readability:
            findings.append(
                f"Layout hierarchy/readability is weak on page(s) {', '.join(str(item) for item in low_readability)}."
            )
        dense_pages = [page["page_index"] for page in page_reviews if int(page.get("density_score") or 0) < 55]
        if dense_pages:
            findings.append(
                f"Text density/clutter appears high on page(s) {', '.join(str(item) for item in dense_pages)}."
            )
        low_brand = [page["page_index"] for page in page_reviews if int(page.get("brand_alignment_score") or 0) < 55]
        if low_brand:
            findings.append(
                f"Visual brand alignment looks weak on page(s) {', '.join(str(item) for item in low_brand)}."
            )
        low_hierarchy = [page["page_index"] for page in page_reviews if int(page.get("hierarchy_score") or 0) < 55]
        if low_hierarchy:
            findings.append(
                f"Headline hierarchy looks weak on page(s) {', '.join(str(item) for item in low_hierarchy)}."
            )
        crowded_pages = [page["page_index"] for page in page_reviews if int(page.get("crowding_score") or 0) < 55]
        if crowded_pages:
            findings.append(
                f"Edge crowding or overlapping text elements appear on page(s) {', '.join(str(item) for item in crowded_pages)}."
            )
        unbalanced_pages = [page["page_index"] for page in page_reviews if int(page.get("page_balance_score") or 0) < 55]
        if unbalanced_pages:
            findings.append(
                f"Page balance feels off on page(s) {', '.join(str(item) for item in unbalanced_pages)}."
            )
        if not findings and expected_prompt:
            findings.append("Visual review did not detect major prompt-alignment, readability, or density issues.")
        return findings[:6]

    @staticmethod
    def _document_segments_from_page_reviews(
        page_reviews: list[dict[str, Any]],
        *,
        asset_kind: str,
    ) -> list[dict[str, Any]]:
        if asset_kind not in {"document", "presentation", "image"}:
            return []
        segments: list[dict[str, Any]] = []
        for page_review in page_reviews[:24]:
            excerpt = str(page_review.get("ocr_text_excerpt") or "").strip()
            words = excerpt.split()
            heading_excerpt = " ".join(words[:8]).strip()
            segments.append(
                {
                    "page_index": int(page_review.get("page_index") or 0),
                    "heading_excerpt": heading_excerpt,
                    "text_excerpt": excerpt[:220],
                    "dominant_region": str((page_review.get("region_diagnostics") or {}).get("dominant_region") or "none"),
                    "text_box_count": int(page_review.get("text_box_count") or 0),
                    "word_count": int(page_review.get("word_count") or 0),
                    "ocr_confidence_score": int(page_review.get("ocr_confidence_score") or 0),
                }
            )
        return segments

    @staticmethod
    def _region_overview_from_pages(page_reviews: list[dict[str, Any]]) -> dict[str, Any]:
        overview = {
            "dominant_regions": [],
            "top_region_count": 0,
            "middle_region_count": 0,
            "bottom_region_count": 0,
            "edge_crowding_pages": 0,
            "overlap_pages": 0,
        }
        dominant_regions: list[str] = []
        for page_review in page_reviews:
            region = page_review.get("region_diagnostics") if isinstance(page_review.get("region_diagnostics"), dict) else {}
            dominant = str(region.get("dominant_region") or "").strip()
            if dominant:
                dominant_regions.append(dominant)
            distribution = region.get("vertical_distribution") if isinstance(region.get("vertical_distribution"), dict) else {}
            overview["top_region_count"] += int(distribution.get("top") or 0)
            overview["middle_region_count"] += int(distribution.get("middle") or 0)
            overview["bottom_region_count"] += int(distribution.get("bottom") or 0)
            if int(region.get("edge_crowding_count") or 0) > 0:
                overview["edge_crowding_pages"] += 1
            if int(region.get("overlap_count") or 0) > 0:
                overview["overlap_pages"] += 1
        overview["dominant_regions"] = dominant_regions[:12]
        return overview

    @classmethod
    def _build_visual_page_review(
        cls,
        *,
        page_index: int,
        image_path: str,
        analysis: dict[str, Any],
        expected_prompt: str,
        page_text: str,
        brand_context: dict[str, Any],
        reference_style_profile: dict[str, Any],
    ) -> dict[str, Any]:
        labels = [
            str(item.get("desc") or "").strip()
            for item in (analysis.get("labels") or [])
            if isinstance(item, dict) and str(item.get("desc") or "").strip()
        ]
        structured_text = [
            entry
            for entry in (analysis.get("structured_text") or [])
            if isinstance(entry, dict)
        ]
        analysis_text = " ".join(
            str(entry.get("text") or entry.get("desc") or "").strip()
            for entry in structured_text
            if str(entry.get("text") or entry.get("desc") or "").strip()
        ).strip()
        observed_text = " ".join(part for part in [str(page_text or "").strip(), analysis_text, " ".join(labels)] if part).strip()
        dominant_colors = [
            str(item.get("hex") or item.get("hex_code") or "").strip().upper()
            for item in (analysis.get("dominant_colors") or [])
            if isinstance(item, dict) and str(item.get("hex") or item.get("hex_code") or "").strip()
        ]
        if not dominant_colors:
            dominant_colors = [
                str(item.get("hex") or item.get("hex_code") or "").strip().upper()
                for item in (analysis.get("text_element_colors") or [])
                if isinstance(item, dict) and str(item.get("hex") or item.get("hex_code") or "").strip()
            ]
        design_style = str(analysis.get("design_style") or "").strip()
        visual_mood = str(analysis.get("visual_mood") or "").strip()
        composition_style = str(analysis.get("composition_style") or analysis.get("layout_type") or "").strip()
        typography_dna = analysis.get("typography_dna") if isinstance(analysis.get("typography_dna"), dict) else {}
        component_motifs = analysis.get("component_motifs") if isinstance(analysis.get("component_motifs"), dict) else {}
        font_families = [
            str(item.get("name") or item.get("family") or "").strip()
            for item in (analysis.get("font_families") or analysis.get("fonts") or [])
            if isinstance(item, dict) and str(item.get("name") or item.get("family") or "").strip()
        ]
        word_count = len(re.findall(r"\b\w+\b", observed_text))
        line_count = max(len([line for line in observed_text.splitlines() if line.strip()]), 1) if observed_text else 0
        box_heights: list[int] = []
        box_area = 0
        for entry in structured_text:
            bbox = entry.get("bounding_box") if isinstance(entry.get("bounding_box"), dict) else {}
            width = int(bbox.get("w", bbox.get("width", 0)) or 0)
            height = int(bbox.get("h", bbox.get("height", 0)) or 0)
            if width > 0 and height > 0:
                box_heights.append(height)
                box_area += width * height
        canvas_size = cls._image_canvas_size(image_path)
        canvas_width, canvas_height = canvas_size if canvas_size else (0, 0)
        layout_regions = cls._layout_region_diagnostics(
            structured_text=structured_text,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        hierarchy_signal = 0.0
        if box_heights:
            hierarchy_signal = min(max(max(box_heights) / max(min(box_heights), 1), 1.0), 4.0)
        matched_prompt_terms, missing_prompt_terms = cls._prompt_term_diagnostics(expected_prompt, observed_text, labels)
        prompt_alignment_score = cls._prompt_alignment_score(expected_prompt, observed_text, labels)
        layout_readability_score = cls._layout_readability_score(
            word_count=word_count,
            line_count=line_count,
            text_box_count=len(structured_text),
            hierarchy_signal=hierarchy_signal,
        )
        density_score = cls._density_score(
            word_count=word_count,
            text_box_count=len(structured_text),
            box_area=box_area,
        )
        hierarchy_score = cls._hierarchy_score(
            hierarchy_signal=hierarchy_signal,
            headline_prominence=layout_regions["headline_prominence"],
        )
        crowding_score = cls._crowding_score(
            text_box_count=len(structured_text),
            edge_crowding_count=layout_regions["edge_crowding_count"],
            overlap_count=layout_regions["overlap_count"],
            text_coverage_ratio=layout_regions["text_coverage_ratio"],
        )
        page_balance_score = cls._page_balance_score(layout_regions["vertical_distribution"])
        style_alignment_score = cls._style_alignment_score(
            brand_context=brand_context,
            design_style=design_style,
            composition_style=composition_style,
        )
        mood_alignment_score = cls._mood_alignment_score(
            brand_context=brand_context,
            visual_mood=visual_mood,
        )
        typography_alignment_score = cls._typography_alignment_score(
            brand_context=brand_context,
            typography_dna=typography_dna,
            font_families=font_families,
        )
        motif_alignment_score = cls._motif_alignment_score(
            brand_context=brand_context,
            component_motifs=component_motifs,
        )
        reference_similarity_score = cls._reference_similarity_score(
            reference_style_profile=reference_style_profile,
            design_style=design_style,
            visual_mood=visual_mood,
            composition_style=composition_style,
            typography_dna=typography_dna,
            component_motifs=component_motifs,
            font_families=font_families,
        )
        brand_alignment_score = cls._brand_alignment_score(
            brand_context=brand_context,
            observed_text=observed_text,
            labels=labels,
            dominant_colors=dominant_colors,
            style_alignment_score=style_alignment_score,
            mood_alignment_score=mood_alignment_score,
            typography_alignment_score=typography_alignment_score,
            motif_alignment_score=motif_alignment_score,
            reference_similarity_score=reference_similarity_score,
        )
        page_findings = cls._page_findings(
            prompt_alignment_score=prompt_alignment_score,
            layout_readability_score=layout_readability_score,
            density_score=density_score,
            hierarchy_score=hierarchy_score,
            crowding_score=crowding_score,
            page_balance_score=page_balance_score,
            missing_prompt_terms=missing_prompt_terms,
        )
        ocr_confidence_score = cls._ocr_confidence_score(
            structured_text=structured_text,
            observed_text=observed_text,
            warning_count=0,
        )
        dominant_region = max(layout_regions["vertical_distribution"].items(), key=lambda item: item[1])[0] if any(layout_regions["vertical_distribution"].values()) else "none"
        return {
            "page_index": page_index,
            "image_path": image_path,
            "ocr_text_excerpt": observed_text[:500],
            "label_hits": labels[:8],
            "text_box_count": len(structured_text),
            "word_count": word_count,
            "line_count": line_count,
            "prompt_alignment_score": prompt_alignment_score,
            "semantic_consistency_score": prompt_alignment_score,
            "layout_readability_score": layout_readability_score,
            "density_score": density_score,
            "hierarchy_score": hierarchy_score,
            "crowding_score": crowding_score,
            "page_balance_score": page_balance_score,
            "ocr_confidence_score": ocr_confidence_score,
            "brand_alignment_score": brand_alignment_score,
            "style_alignment_score": style_alignment_score,
            "mood_alignment_score": mood_alignment_score,
            "typography_alignment_score": typography_alignment_score,
            "motif_alignment_score": motif_alignment_score,
            "reference_similarity_score": reference_similarity_score,
            "dominant_colors": dominant_colors[:8],
            "design_style": design_style or None,
            "visual_mood": visual_mood or None,
            "composition_style": composition_style or None,
            "typography_observed": {
                "heading_style": str(typography_dna.get("heading_style") or "").strip() or None,
                "text_alignment": str(typography_dna.get("text_alignment") or "").strip() or None,
                "dominant_case": str(typography_dna.get("dominant_case") or "").strip() or None,
                "emphasis_pattern": str(typography_dna.get("emphasis_pattern") or "").strip() or None,
                "font_families": font_families[:4],
            },
            "motif_keys": [
                str(key).replace("_", " ")
                for key, value in component_motifs.items()
                if value
            ][:8],
            "matched_prompt_terms": matched_prompt_terms[:8],
            "missing_prompt_terms": missing_prompt_terms[:8],
            "page_findings": page_findings[:6],
            "region_diagnostics": {
                "dominant_region": dominant_region,
                "edge_crowding_count": layout_regions["edge_crowding_count"],
                "overlap_count": layout_regions["overlap_count"],
                "text_coverage_ratio": round(layout_regions["text_coverage_ratio"], 4),
                "vertical_distribution": layout_regions["vertical_distribution"],
                "headline_prominence": round(layout_regions["headline_prominence"], 2),
            },
        }

    @staticmethod
    def _ocr_confidence_score(
        *,
        structured_text: list[dict[str, Any]],
        observed_text: str,
        warning_count: int,
    ) -> int:
        confidence_values: list[float] = []
        for entry in structured_text:
            raw = entry.get("confidence", entry.get("score"))
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value <= 1.0:
                value *= 100.0
            confidence_values.append(max(0.0, min(100.0, value)))
        if confidence_values:
            base = sum(confidence_values) / max(len(confidence_values), 1)
        else:
            word_count = len(re.findall(r"\b\w+\b", observed_text or ""))
            if word_count >= 40:
                base = 82.0
            elif word_count >= 15:
                base = 72.0
            elif word_count >= 5:
                base = 60.0
            elif observed_text:
                base = 48.0
            else:
                base = 18.0
        base -= warning_count * 6.0
        return max(0, min(100, int(round(base))))

    @classmethod
    def _visual_review_report(cls, asset_review_blocks: list[dict[str, Any]]) -> dict[str, Any]:
        visual_blocks = [
            block
            for block in asset_review_blocks
            if isinstance(block.get("visual_review"), dict) and block.get("visual_review")
        ]
        if not visual_blocks:
            return {
                "asset_count": 0,
                "page_count": 0,
                "prompt_alignment_score": 100,
                "layout_readability_score": 100,
                "density_score": 100,
                "brand_alignment_score": 100,
                "style_alignment_score": 100,
                "mood_alignment_score": 100,
                "typography_alignment_score": 100,
                "motif_alignment_score": 100,
                "reference_similarity_score": 100,
                "aesthetic_consistency_score": 100,
                "hierarchy_score": 100,
                "crowding_score": 100,
                "page_balance_score": 100,
                "ocr_confidence_score": 100,
                "visual_diagnostic_score": 100,
                "findings": [],
                "page_reviews": [],
                "document_segments": [],
                "region_overview": {},
            }
        page_reviews = [
            {
                "asset_id": block.get("asset_id"),
                "asset_name": block.get("asset_name"),
                **page_review,
            }
            for block in visual_blocks
            for page_review in (block.get("visual_review", {}).get("page_reviews") or [])
            if isinstance(page_review, dict)
        ]
        findings: list[str] = []
        for block in visual_blocks:
            for finding in (block.get("visual_review", {}).get("findings") or []):
                text = str(finding or "").strip()
                if text and text not in findings:
                    findings.append(text)
        def avg(field: str) -> int:
            return max(
                0,
                min(
                    100,
                    int(
                        round(
                            sum(float((block.get("visual_review", {}).get("diagnostics") or {}).get(field) or 0.0) for block in visual_blocks)
                            / max(len(visual_blocks), 1)
                        )
                    ),
                ),
            )
        aesthetic_consistency_score = cls._aesthetic_consistency_score(page_reviews)
        return {
            "asset_count": len(visual_blocks),
            "page_count": len(page_reviews),
            "prompt_alignment_score": avg("prompt_alignment_score"),
            "layout_readability_score": avg("layout_readability_score"),
            "density_score": avg("density_score"),
            "brand_alignment_score": avg("brand_alignment_score"),
            "style_alignment_score": avg("style_alignment_score"),
            "mood_alignment_score": avg("mood_alignment_score"),
            "typography_alignment_score": avg("typography_alignment_score"),
            "motif_alignment_score": avg("motif_alignment_score"),
            "reference_similarity_score": avg("reference_similarity_score"),
            "aesthetic_consistency_score": aesthetic_consistency_score,
            "hierarchy_score": avg("hierarchy_score"),
            "crowding_score": avg("crowding_score"),
            "page_balance_score": avg("page_balance_score"),
            "ocr_confidence_score": avg("ocr_confidence_score"),
            "visual_diagnostic_score": avg("visual_diagnostic_score"),
            "findings": findings[:8],
            "page_reviews": page_reviews[:20],
            "document_segments": [
                {
                    "asset_id": block.get("asset_id"),
                    "asset_name": block.get("asset_name"),
                    **segment,
                }
                for block in visual_blocks
                for segment in (block.get("visual_review", {}).get("document_segments") or [])
                if isinstance(segment, dict)
            ][:24],
            "region_overview": cls._region_overview_from_pages(page_reviews),
        }
