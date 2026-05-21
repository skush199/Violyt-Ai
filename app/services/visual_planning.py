from __future__ import annotations

from typing import Any

from app.services.content_planning import ContentPlanningService
from app.services.format_family_planning import FormatFamilyPlanningService
from app.services.research_editorial_planning import ResearchEditorialPlanningService


class VisualPlanningService:
    def __init__(self) -> None:
        self.content_planning = ContentPlanningService()
        self.research_editorial = ResearchEditorialPlanningService()
        self.format_family_planning = FormatFamilyPlanningService()

    def build_visual_plan(
        self,
        *,
        prompt: str,
        studio_panel: dict[str, Any] | None,
        brand_context: dict[str, Any] | None,
        persona_context: dict[str, Any] | None,
        objective_context: dict[str, Any] | None,
        knowledge_brief: list[dict[str, Any]] | None,
        live_research: dict[str, Any] | None,
        content_format_guide: dict[str, Any] | None = None,
        deliverable_type: str | None = None,
        template_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        research_editorial_brief = self.research_editorial.build(
            prompt=prompt,
            studio_panel=studio_panel,
            brand_context=brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            knowledge_brief=knowledge_brief,
            live_research=live_research,
            content_format_guide=content_format_guide,
            deliverable_type=deliverable_type,
            template_context=template_context,
        )
        format_family_plan = self.format_family_planning.build(
            studio_panel=studio_panel,
            deliverable_type=deliverable_type,
            research_editorial_brief=research_editorial_brief,
        )
        preferred_slide_count = int(
            research_editorial_brief.get("preferred_slide_count")
            or format_family_plan.get("preferred_slide_count")
            or 0
        )
        return {
            "research_editorial_brief": research_editorial_brief,
            "format_family_plan": format_family_plan,
            "content_plan": self.content_planning.derive_content_plan(
                deliverable_type=deliverable_type or "visual_generation",
                format_family_plan=format_family_plan,
                research_editorial_brief=research_editorial_brief,
                planning_family="content",
            ),
            "visual_plan": {
                "planning_family": "visual",
                "format_family": str(format_family_plan.get("family") or "").strip() or "static",
                "primary_unit": str(format_family_plan.get("primary_unit") or "").strip() or "frame",
                "body_shape": str(format_family_plan.get("body_shape") or "").strip() or "modular",
                "density_target": str(format_family_plan.get("density_target") or "").strip() or "medium",
                "preferred_slide_count": preferred_slide_count,
                "page_strategy": "multi_page" if preferred_slide_count > 1 else "single_page",
                "render_mode": "ai_final_render",
                "execution_mode": "multi_page_sequence" if preferred_slide_count > 1 else "single_frame_composition",
                "visual_sequence_expectation": (
                    "distinct_page_compositions"
                    if preferred_slide_count > 1
                    else "single_focal_composition"
                ),
                "research_mode": str(research_editorial_brief.get("mode") or "").strip() or "standard",
            },
        }
