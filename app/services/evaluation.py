from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from app.ai.brand_intelligence import BrandIntelligenceService
from app.core.exceptions import NotFoundError
from app.repositories.brand import BrandSpaceRepository, ObjectiveRepository, PersonaRepository
from app.services.artifact_state import ArtifactStateService
from app.services.text_content import TextContentService


class EvaluationService:
    MAX_MULTIMODAL_IMAGES = 3

    def __init__(self, session) -> None:
        self.session = session
        self.helper = TextContentService(session)
        self.providers = self.helper.providers
        self.brands = BrandSpaceRepository(session)
        self.personas = PersonaRepository(session)
        self.objectives = ObjectiveRepository(session)
        self.tone = self.helper.tone
        self.artifacts = ArtifactStateService()

    async def evaluate(
        self,
        *,
        tenant_id: UUID,
        brand_space_id: UUID,
        session,
        prompt: str,
        persona_id=None,
        objective_id=None,
        reference_asset_ids=None,
    ) -> dict[str, Any]:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        personas = await self.personas.list_by_brand(brand_space_id, tenant_id)
        objectives = await self.objectives.list_by_brand(brand_space_id, tenant_id)
        selected_persona = next((item for item in personas if item.id == persona_id), None)
        selected_objective = next((item for item in objectives if item.id == objective_id), None)
        brand_context = dict(getattr(brand, "resolved_brand_context", {}) or {})
        persona_context = BrandIntelligenceService.persona_to_dict(selected_persona)
        objective_context = BrandIntelligenceService.objective_to_dict(selected_objective)

        reviewed_asset_ids: list[str] = []
        asset_review_blocks = await self.helper._review_text_from_assets(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            reference_asset_ids=reference_asset_ids or [],
            review_prompt=prompt,
            brand_context=brand_context,
        )
        if asset_review_blocks:
            reviewed_asset_ids = [block["asset_id"] for block in asset_review_blocks if block.get("asset_id")]
        target_text = self.helper._evaluation_target_text(
            prompt=prompt,
            session=session,
            asset_review_blocks=asset_review_blocks,
        )
        if not target_text:
            target_text = str(session.conversational_context.get("last_text_output") or "").strip()
        report = self.tone.evaluate(
            content=target_text,
            brand_context=brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
        )
        visual_asset_review_count = sum(
            1 for block in asset_review_blocks if isinstance(block.get("visual_review"), dict) and block.get("visual_review")
        )
        asset_scope = "visual_asset_backed" if visual_asset_review_count else ("asset_backed" if asset_review_blocks else "text_only")
        asset_coverage_score = self.helper._asset_coverage_score(asset_review_blocks)
        asset_diagnostics = self.helper._asset_diagnostics(asset_review_blocks)
        visual_review_report = self.helper._visual_review_report(asset_review_blocks)
        asset_gaps = [
            block["gap_note"]
            for block in asset_review_blocks
            if str(block.get("gap_note") or "").strip()
        ]
        response = {
            "mode": "evaluation",
            "review_type": "asset_tone_brand_consistency" if asset_review_blocks else "tone_brand_consistency",
            "evaluation_scope": asset_scope,
            "reviewed_content": target_text,
            "scorecard": {
                "overall_score": int(report.get("score") or 0),
                "brand_alignment_score": int((report.get("persuasion_dimensions") or {}).get("brand_alignment") or 0),
                "clarity_score": int((report.get("persuasion_dimensions") or {}).get("clarity") or 0),
                "proof_strength_score": int((report.get("persuasion_dimensions") or {}).get("proof_strength") or 0),
                "objection_handling_score": int((report.get("persuasion_dimensions") or {}).get("objection_handling") or 0),
                "cta_strength_score": int((report.get("persuasion_dimensions") or {}).get("cta_strength") or 0),
                "asset_coverage_score": asset_coverage_score,
                "source_quality_score": asset_diagnostics["source_quality_score"],
                "document_structure_score": asset_diagnostics["document_structure_score"],
                "visual_diagnostic_score": asset_diagnostics["visual_diagnostic_score"],
                "hierarchy_score": asset_diagnostics["hierarchy_score"],
                "crowding_score": asset_diagnostics["crowding_score"],
                "page_balance_score": asset_diagnostics["page_balance_score"],
                "ocr_confidence_score": asset_diagnostics["ocr_confidence_score"],
            },
            "matched_signals": report.get("matched_signals", []),
            "deviations": report.get("deviations", []),
            "rewrite_suggestions": report.get("rewrite_suggestions", []),
            "quality_summary": report.get("quality_summary", []),
            "field_guidance": report.get("field_guidance", {}),
            "review_sources": asset_review_blocks,
            "reviewed_asset_ids": reviewed_asset_ids,
            "asset_gaps": asset_gaps,
            "asset_diagnostics": asset_diagnostics,
            "visual_review_report": visual_review_report,
            "source_observations": self.helper._source_observations(asset_review_blocks),
            "summary": self.helper._evaluation_summary(report, asset_review_blocks=asset_review_blocks, asset_coverage_score=asset_coverage_score),
        }
        multimodal_review = self._multimodal_visual_review(
            prompt=prompt,
            asset_review_blocks=[item for item in asset_review_blocks if isinstance(item, dict)],
        )
        if multimodal_review:
            response["multimodal_review"] = multimodal_review
            response["scorecard"]["multimodal_visual_score"] = int(multimodal_review.get("score") or 0)
            response["scorecard"]["visual_diagnostic_score"] = int(
                round(
                    (
                        float(response["scorecard"].get("visual_diagnostic_score") or 0)
                        + float(multimodal_review.get("score") or 0)
                    )
                    / 2.0
                )
            )
        response["artifact_state"] = self.artifacts.build_content_state(
            mode="evaluation",
            prompt=prompt,
            studio_panel=session.studio_panel if isinstance(session.studio_panel, dict) else {},
            evaluation_history=[self.artifacts.build_evaluation_entry(response)],
            source_linked_artifacts={"reviewed_asset_ids": reviewed_asset_ids},
        )
        if multimodal_review:
            history = response["artifact_state"].get("evaluation_history")
            if isinstance(history, list) and history:
                latest = history[-1]
                if isinstance(latest, dict):
                    latest["multimodal_review"] = multimodal_review
        return response

    def _multimodal_visual_review(
        self,
        *,
        prompt: str,
        asset_review_blocks: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        provider = self.providers.get_text_provider("generation")
        client = getattr(provider, "client", None)
        if client is None or getattr(provider, "provider_name", "") != "openai":
            return None

        image_contents: list[dict[str, Any]] = []
        reviewed_asset_ids: list[str] = []
        for block in asset_review_blocks:
            asset_kind = str(block.get("asset_kind") or "").strip().lower()
            storage_path = str(block.get("storage_path") or "").strip()
            if asset_kind != "image" or not storage_path:
                continue
            file_path = Path(storage_path)
            if not file_path.exists():
                continue
            try:
                encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
            except OSError:
                continue
            image_contents.append({"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"})
            reviewed_asset_ids.append(str(block.get("asset_id") or "").strip())
            if len(image_contents) >= self.MAX_MULTIMODAL_IMAGES:
                break

        if not image_contents:
            return None

        review_prompt = (
            "You are a visual brand and composition reviewer. "
            "Review the provided visual asset(s) against the prompt and return JSON only with keys: "
            "score, strengths, issues, alignment_summary. "
            "Score must be 0-100. Focus on semantic match to prompt, hierarchy, readability, clutter, and brand fit.\n\n"
            f"Prompt: {prompt}"
        )
        fallback = {"score": 0, "strengths": [], "issues": [], "alignment_summary": ""}
        try:
            response = client.responses.create(
                model=getattr(provider.settings, "llm_model", None),
                input=[
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": [{"type": "input_text", "text": review_prompt}, *image_contents]},
                ],
                text={"format": {"type": "json_object"}},
            )
            parsed = response.output_text
            if not parsed:
                return None
            result = json.loads(parsed)
        except Exception:
            result = fallback
        if not isinstance(result, dict):
            return None
        return {
            "score": max(0, min(100, int(result.get("score") or 0))),
            "strengths": [str(item).strip() for item in (result.get("strengths") or []) if str(item).strip()][:6],
            "issues": [str(item).strip() for item in (result.get("issues") or []) if str(item).strip()][:6],
            "alignment_summary": str(result.get("alignment_summary") or "").strip(),
            "reviewed_asset_ids": [item for item in reviewed_asset_ids if item],
        }
