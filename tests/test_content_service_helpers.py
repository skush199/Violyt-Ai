from contextlib import contextmanager
from uuid import uuid4
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError
from reportlab.pdfgen import canvas as pdf_canvas

from app.models.content import ContentVersion, GeneratedAsset
from app.models.knowledge import KnowledgeAsset
from app.models.knowledge import TemplateMetadata
from app.ai.layout_decision import LayoutDecision
from app.schemas.content import ToneCheckRequest
from app.services.content import ContentService


def _build_content_version(*, explainability_metadata: dict | None = None) -> ContentVersion:
    return ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a LinkedIn carousel about fixed-income confidence.",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        generated_payload={},
        blueprint_payload={},
        explainability_metadata=explainability_metadata or {},
        tone_feedback={},
    )


def test_merge_studio_panel_preserves_existing_size_and_overrides_fields() -> None:
    merged = ContentService._merge_studio_panel(
        {
            "format": "static",
            "platform_preset": "linkedin",
            "file_type": "png",
            "size": {"width": 1200, "height": 627},
        },
        {
            "file_type": "pdf",
            "size": {"height": 800},
        },
    )
    assert merged["platform_preset"] == "linkedin"
    assert merged["file_type"] == "pdf"
    assert merged["size"] == {"width": 1200, "height": 800}


def test_tone_check_request_accepts_version_or_structured_payload_without_raw_content() -> None:
    version_only = ToneCheckRequest(content_version_id=uuid4())
    structured_only = ToneCheckRequest(
        content_payload={
            "headline": "Close the books faster",
            "body": "Guided onboarding helps teams move faster.",
            "cta": "Book a demo",
        }
    )

    assert version_only.content_version_id is not None
    assert structured_only.content_payload["headline"] == "Close the books faster"


def test_tone_check_request_requires_content_or_equivalent_source() -> None:
    with pytest.raises(ValidationError, match="Provide content, content_payload, or content_version_id"):
        ToneCheckRequest()


def test_template_context_ignores_semantically_conflicting_layout_dna_for_selected_carousel() -> None:
    template_meta = SimpleNamespace(
        zone_map={
            "zones": [{"role": "headline", "x": 0.05, "y": 0.01, "w": 0.7, "h": 0.12}],
            "editorial_dna": {
                "headline_patterns": ["Bond Market", "See the bond market the way professionals do"],
            },
            "subject_semantics": {
                "primary_subjects": ["bond market", "yield curves", "government spreads"],
            },
        },
        sizing_rules={"page_count": 4},
        platform_rules={},
        editable_fields=["headline", "body", "image"],
        export_rules={"supported_formats": ["png"]},
    )

    context = ContentService._build_template_context_payload(
        prompt="Write a LinkedIn carousel on the India-New Zealand FTA.",
        template_meta=template_meta,
        selected_template_id="fta-template-id",
        selected_template_name="FTA (3)",
        template_recommendations=[
            {
                "template_id": "fta-template-id",
                "name": "FTA (3)",
                "metadata": {
                    "format_family": "carousel",
                    "page_count": 4,
                    "summary": "India New Zealand free trade agreement tariff investment mobility",
                },
            }
        ],
        reference_assets=[
            {
                "storage_path": "reference_creatives/FTA-3.pdf",
                "mime_type": "application/pdf",
                "metadata": {
                    "label": "FTA (3)",
                    "summary": "India New Zealand trade agreement zero duty investment students visas",
                    "format_family": "carousel",
                    "page_count": 4,
                },
            }
        ],
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
    )

    assert context is not None
    assert context["sample_metadata_status"] == "template_layout_context_ignored_due_to_semantic_mismatch"
    assert "editorial_dna" not in context
    assert "subject_semantics" not in context
    assert "zone_map" not in context
    assert context["sequence_pack"]["selected_template_name"] == "FTA (3)"
    assert not (context["sequence_pack"]["slides"][0].get("zone_map") or {}).get("zones")


def test_template_context_uses_prompt_evidence_when_selected_sample_metadata_is_thin() -> None:
    template_meta = SimpleNamespace(
        zone_map={
            "zones": [{"role": "image", "x": 0.11, "y": 0.2, "w": 0.14, "h": 0.14}],
            "editorial_dna": {
                "headline_patterns": ["Bond Market", "See the bond market the way professionals do"],
            },
            "subject_semantics": {
                "primary_subjects": ["bond market", "yield curves", "government spreads"],
                "financial_objects": ["bonds", "line graphs", "spreads"],
            },
        },
        sizing_rules={"page_count": 4},
        platform_rules={},
        editable_fields=["headline", "body", "image"],
        export_rules={"supported_formats": ["png"]},
    )

    context = ContentService._build_template_context_payload(
        prompt="Write a LinkedIn carousel for Jiraaf on the India-New Zealand FTA signed on 27 April 2026.",
        template_meta=template_meta,
        selected_template_id="fta-template-id",
        selected_template_name="FTA (3)",
        template_recommendations=[
            {
                "template_id": "fta-template-id",
                "name": "FTA (3)",
                "metadata": {"format_family": "carousel", "page_count": 4},
            }
        ],
        reference_assets=[
            {
                "storage_path": "reference_creatives/FTA-3-7af041a72ab6483e8dee0fb827a4fd9d.pdf",
                "mime_type": "application/pdf",
                "metadata": {"label": "FTA (3)", "format_family": "carousel", "page_count": 4},
            }
        ],
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
    )

    assert context is not None
    assert context["sample_metadata_status"] == "template_layout_context_ignored_due_to_semantic_mismatch"
    assert "editorial_dna" not in context
    assert "subject_semantics" not in context
    assert "zone_map" not in context
    assert context["sequence_pack"]["selected_template_name"] == "FTA (3)"


def test_rewrite_compiled_context_reuses_stored_guide_aware_context() -> None:
    stored_compiled_context = {
        "brand_copy_brief": {"brand_name": "Jiraaf"},
        "content_format_brief": {"platform_preset": "linkedin", "format": "carousel", "summary": "Use one idea per page."},
    }
    original = _build_content_version(explainability_metadata={"compiled_context": stored_compiled_context})
    service = ContentService.__new__(ContentService)
    service.orchestrator = SimpleNamespace(
        compiler=SimpleNamespace(
            _content_format_brief=lambda *args, **kwargs: pytest.fail("stored guide-aware context should not be backfilled"),
            compile=lambda **kwargs: pytest.fail("stored guide-aware context should not be rebuilt"),
        )
    )

    result = service._rewrite_compiled_context(
        original=original,
        source_prompt=original.prompt,
        resolved_brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        session=SimpleNamespace(conversational_context={"message_count": 1}),
        content_format_guide={"summary": "Client guide"},
    )

    assert result == stored_compiled_context
    assert result is not stored_compiled_context


def test_rewrite_compiled_context_backfills_only_missing_content_format_brief() -> None:
    stored_compiled_context = {
        "brand_copy_brief": {"brand_name": "Jiraaf"},
        "audience_brief": {"language_preference": "plain English"},
    }
    expected_brief = {
        "platform_preset": "linkedin",
        "format": "carousel",
        "summary": "Use one idea per page.",
    }
    original = _build_content_version(explainability_metadata={"compiled_context": stored_compiled_context})
    service = ContentService.__new__(ContentService)
    service.orchestrator = SimpleNamespace(
        compiler=SimpleNamespace(
            _content_format_brief=lambda guide, panel: expected_brief,
            compile=lambda **kwargs: pytest.fail("stored compiled context should be backfilled, not rebuilt"),
        )
    )

    result = service._rewrite_compiled_context(
        original=original,
        source_prompt=original.prompt,
        resolved_brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        session=SimpleNamespace(conversational_context={"message_count": 1}),
        content_format_guide={"summary": "Client guide"},
    )

    assert result["brand_copy_brief"] == stored_compiled_context["brand_copy_brief"]
    assert result["audience_brief"] == stored_compiled_context["audience_brief"]
    assert result["content_format_brief"] == expected_brief


def test_rewrite_compiled_context_rebuilds_with_content_format_guide_when_missing() -> None:
    original = _build_content_version(
        explainability_metadata={
            "session_memory": {"recent_topics": ["fixed income"]},
            "layout_decision": {"mode": "template"},
        }
    )
    captured: dict[str, object] = {}
    rebuilt_context = {
        "brand_copy_brief": {"brand_name": "Jiraaf"},
        "content_format_brief": {"platform_preset": "linkedin", "format": "carousel", "summary": "Use one idea per page."},
    }
    service = ContentService.__new__(ContentService)
    service.orchestrator = SimpleNamespace(
        compiler=SimpleNamespace(
            _content_format_brief=lambda *args, **kwargs: pytest.fail("full rebuild should call compile directly"),
            compile=lambda **kwargs: captured.update(kwargs) or rebuilt_context,
        )
    )

    result = service._rewrite_compiled_context(
        original=original,
        source_prompt=original.prompt,
        resolved_brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        session=SimpleNamespace(conversational_context={"message_count": 3}),
        content_format_guide={"summary": "Client guide"},
    )

    assert result == rebuilt_context
    assert captured["content_format_guide"] == {"summary": "Client guide"}
    assert captured["session_memory"] == {"recent_topics": ["fixed income"]}
    assert captured["layout_decision"] == {"mode": "template"}


def test_rebalance_sequence_pack_story_roles_adds_editorial_progression() -> None:
    slides = [
        {"slide_index": 1, "story_role": "context", "structural_cues": ["context setup"]},
        {"slide_index": 2, "story_role": "context", "structural_cues": ["context setup"]},
        {"slide_index": 3, "story_role": "context", "structural_cues": ["context setup"]},
        {"slide_index": 4, "story_role": "context", "structural_cues": ["context setup"]},
        {"slide_index": 5, "story_role": "context", "structural_cues": ["context setup"]},
    ]

    rebalanced = ContentService._rebalance_sequence_pack_story_roles(slides)

    assert [slide["story_role"] for slide in rebalanced] == [
        "hook",
        "structure",
        "undercovered_angle",
        "strategic_meaning",
        "takeaway",
    ]
    assert rebalanced[0]["structural_cues"] == ["cover hook"]
    assert rebalanced[-1]["structural_cues"] == ["takeaway close"]


def test_apply_template_context_surface_policy_to_planning_hints_marks_style_reference_only() -> None:
    planning_hints = {
        "mode": "adapted_template",
        "asset_strategy": {
            "use_template_background": True,
            "use_generated_image": True,
            "use_brand_reference_assets": True,
        },
    }
    template_context = {
        "sequence_pack": {
            "surface_policy": "style_reference_only",
            "slide_count": 7,
            "slides": [{"slide_index": 1, "reference_asset_path": "tenant/reference/sample-1.png"}],
        }
    }

    updated = ContentService._apply_template_context_surface_policy_to_planning_hints(
        planning_hints,
        template_context,
        {"format": "carousel"},
    )

    assert updated["template_surface_policy"] == "style_reference_only"
    assert updated["asset_strategy"]["template_surface_policy"] == "style_reference_only"
    assert updated["asset_strategy"]["use_template_background"] is False
    assert updated["asset_strategy"]["use_generated_image"] is True
    assert updated["asset_strategy"]["supporting_visual_system"] == "reference_assets"


def test_repair_rewrite_payload_preserves_non_targeted_carousel_slides() -> None:
    original = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a LinkedIn carousel about bond mistakes.",
        generated_payload={
            "headline": "Top Bond Mistakes",
            "body": "Original body",
            "cta": "Explore Jiraaf",
            "hashtags": ["#bonds"],
            "metadata": {
                "carousel_slide_specs": [
                    {"slide_index": 1, "headline": "Hook", "supporting_line": "Original 1"},
                    {"slide_index": 2, "headline": "Mistake 1", "supporting_line": "Original 2"},
                    {"slide_index": 3, "headline": "CTA", "supporting_line": "Original 3"},
                ]
            },
        },
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )

    repaired, diagnostics = ContentService._repair_rewrite_payload(
        original,
        {
            "headline": "Rewritten headline",
            "body": "Rewritten body",
            "cta": "Rewritten CTA",
            "metadata": {
                "carousel_slide_specs": [
                    {"slide_index": 1, "headline": "Hook updated", "supporting_line": "Rewritten 1"},
                    {"slide_index": 2, "headline": "Mistake 1 sharper", "supporting_line": "Rewritten 2"},
                    {"slide_index": 3, "headline": "CTA updated", "supporting_line": "Rewritten 3"},
                ]
            },
        },
        "Make slide 2 sharper",
        {"slide_indexes": [2], "preserve_visuals": True, "only_targeted": True},
    )

    assert repaired["headline"] == "Top Bond Mistakes"
    assert repaired["body"] == "Original body"
    assert repaired["cta"] == "Explore Jiraaf"
    assert repaired["metadata"]["carousel_slide_specs"][0]["headline"] == "Hook"
    assert repaired["metadata"]["carousel_slide_specs"][1]["headline"] == "Mistake 1 sharper"
    assert repaired["metadata"]["carousel_slide_specs"][2]["headline"] == "CTA"
    assert diagnostics["updated_slide_indexes"] == [2]


def test_repair_rewrite_payload_preserves_copy_for_layout_only_edits() -> None:
    original = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a LinkedIn carousel about bond mistakes.",
        generated_payload={
            "headline": "Top Bond Mistakes",
            "body": "Original body",
            "cta": "Explore Jiraaf",
            "hashtags": ["#bonds"],
            "metadata": {
                "supporting_line": "Original supporting line",
                "carousel_slide_specs": [
                    {"slide_index": 1, "headline": "Hook", "supporting_line": "Original 1"},
                    {"slide_index": 2, "headline": "Mistake 1", "supporting_line": "Original 2"},
                ],
            },
        },
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )

    repaired, diagnostics = ContentService._repair_rewrite_payload(
        original,
        {
            "headline": "Changed headline",
            "body": "Changed body",
            "cta": "Changed CTA",
            "hashtags": ["#new"],
            "metadata": {
                "supporting_line": "Changed supporting line",
                "carousel_slide_specs": [
                    {"slide_index": 1, "headline": "Hook updated", "supporting_line": "Updated 1"},
                    {"slide_index": 2, "headline": "Mistake updated", "supporting_line": "Updated 2"},
                ],
            },
        },
        "Keep copy, change layout only",
        {"preserve_copy": True, "change_layout": True},
    )

    assert repaired["headline"] == "Top Bond Mistakes"
    assert repaired["body"] == "Original body"
    assert repaired["cta"] == "Explore Jiraaf"
    assert repaired["hashtags"] == ["#bonds"]
    assert repaired["metadata"]["supporting_line"] == "Original supporting line"
    assert repaired["metadata"]["carousel_slide_specs"][0]["headline"] == "Hook"
    assert repaired["metadata"]["carousel_slide_specs"][1]["headline"] == "Mistake 1"
    assert diagnostics["revision_scope_targeted_fields"] == []


def test_build_selective_regeneration_plan_targets_all_slides_when_visuals_are_preserved() -> None:
    original = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a LinkedIn carousel about bond mistakes.",
        generated_payload={
            "headline": "Top Bond Mistakes",
            "body": "Original body",
            "cta": "Explore Jiraaf",
            "hashtags": ["#bonds"],
            "metadata": {
                "carousel_slide_specs": [
                    {"slide_index": 1, "headline": "Hook"},
                    {"slide_index": 2, "headline": "Mistake 1"},
                    {"slide_index": 3, "headline": "CTA"},
                ]
            },
        },
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )

    plan = ContentService._build_selective_regeneration_plan(
        original=original,
        revision_scope={"targeted_fields": ["cta"], "preserve_visuals": True, "only_targeted": True},
    )

    assert plan["targeted_fields"] == ["cta"]
    assert plan["targeted_slide_indexes"] == [1, 2, 3]
    assert plan["reuse_slide_indexes"] == []


def test_build_selective_regeneration_plan_targets_all_slides_for_copy_edits_without_explicit_slide_target() -> None:
    original = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a LinkedIn carousel about bond mistakes.",
        generated_payload={
            "headline": "Top Bond Mistakes",
            "body": "Original body",
            "cta": "Explore Jiraaf",
            "hashtags": ["#bonds"],
            "metadata": {
                "carousel_slide_specs": [
                    {"slide_index": 1, "headline": "Hook"},
                    {"slide_index": 2, "headline": "Mistake 1"},
                    {"slide_index": 3, "headline": "CTA"},
                ]
            },
        },
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )

    plan = ContentService._build_selective_regeneration_plan(
        original=original,
        revision_scope={"targeted_fields": ["headline", "body"], "preserve_visuals": False, "only_targeted": True},
    )

    assert plan["targeted_fields"] == ["body", "headline"]
    assert plan["targeted_slide_indexes"] == [1, 2, 3]
    assert plan["reuse_slide_indexes"] == []


def test_resolve_blueprint_payload_prefers_override_and_updates_export_metadata() -> None:
    stored = {
        "layout_type": "single-panel",
        "zones": [{"zone_id": "headline", "role": "headline", "x": 0, "y": 0, "width": 100, "height": 100}],
        "hierarchy": ["headline"],
        "text_blocks": [{"role": "headline", "text": "Hello"}],
        "image_zones": [],
        "logo_rules": {},
        "cta_placement": {},
        "platform_preset": "instagram",
        "export_format": "png",
        "overflow_strategy": {"mode": "shrink_then_wrap"},
    }
    override = {
        **stored,
        "layout_type": "template",
        "zones": [{"zone_id": "body", "role": "body", "x": 10, "y": 10, "width": 90, "height": 90}],
    }
    resolved = ContentService._resolve_blueprint_payload(
        stored_blueprint=stored,
        template_zone_map={"zones": [{"zone_id": "ignored", "role": "headline", "x": 1, "y": 1, "width": 1, "height": 1}]},
        override_blueprint=override,
        studio_panel={"platform_preset": "linkedin", "file_type": "pdf"},
    )
    assert resolved["layout_type"] == "template"
    assert resolved["zones"][0]["role"] == "body"


def test_resolve_blueprint_payload_uses_template_zone_map_when_no_override() -> None:
    stored = {
        "layout_type": "single-panel",
        "zones": [{"zone_id": "headline", "role": "headline", "x": 0, "y": 0, "width": 100, "height": 100}],
        "hierarchy": ["headline"],
        "text_blocks": [{"role": "headline", "text": "Hello"}],
        "image_zones": [],
        "logo_rules": {},
        "cta_placement": {},
        "platform_preset": "instagram",
        "export_format": "png",
        "overflow_strategy": {"mode": "shrink_then_wrap"},
    }
    resolved = ContentService._resolve_blueprint_payload(
        stored_blueprint=stored,
        template_zone_map={
            "layout_type": "template-layout",
            "zones": [{"zone_id": str(uuid4()), "role": "body", "x": 10, "y": 10, "width": 90, "height": 90}],
        },
        override_blueprint=None,
        studio_panel={"platform_preset": "linkedin", "file_type": "pdf"},
    )
    assert resolved["layout_type"] == "template-layout"
    assert resolved["zones"][0]["role"] == "body"
    assert resolved["platform_preset"] == "linkedin"
    assert resolved["export_format"] == "pdf"


def test_resolve_blueprint_payload_clears_template_identity_when_adaptation_is_style_only() -> None:
    stored = {
        "layout_type": "single-panel",
        "zones": [{"zone_id": "headline", "role": "headline", "x": 0, "y": 0, "width": 100, "height": 100}],
        "hierarchy": ["headline"],
        "text_blocks": [{"role": "headline", "text": "Hello"}],
        "image_zones": [],
        "logo_rules": {},
        "cta_placement": {},
        "platform_preset": "instagram",
        "export_format": "png",
        "overflow_strategy": {"mode": "shrink_then_wrap"},
        "source_mode": "adapted_template",
        "source_template_id": "fd-early-template",
        "adaptation_plan": {"reference_style_only": True, "topic_fit_too_weak": True},
    }

    resolved = ContentService._resolve_blueprint_payload(
        stored_blueprint=stored,
        template_zone_map=None,
        override_blueprint=None,
        studio_panel={"platform_preset": "instagram", "file_type": "png"},
    )

    assert resolved["source_mode"] == "synthesized_layout"
    assert resolved["source_template_id"] is None


def test_resolve_blueprint_payload_converts_normalized_template_zone_map_to_absolute_pixels() -> None:
    stored = {
        "layout_type": "single-panel",
        "zones": [{"zone_id": "headline", "role": "headline", "x": 0, "y": 0, "width": 100, "height": 100}],
        "hierarchy": ["headline"],
        "text_blocks": [{"role": "headline", "text": "Hello"}],
        "image_zones": [],
        "logo_rules": {},
        "cta_placement": {},
        "platform_preset": "instagram",
        "export_format": "png",
        "overflow_strategy": {"mode": "shrink_then_wrap"},
    }
    resolved = ContentService._resolve_blueprint_payload(
        stored_blueprint=stored,
        template_zone_map={
            "layout_type": "template-layout",
            "zones": [
                {"zone_id": "logo", "role": "logo", "x": 0.75, "y": 0.05, "width": 0.22, "height": 0.1},
                {"zone_id": "headline", "role": "headline", "x": 0.1, "y": 0.2, "width": 0.6, "height": 0.1},
            ],
        },
        override_blueprint=None,
        studio_panel={"platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
    )

    logo_zone = next(zone for zone in resolved["zones"] if zone["role"] == "logo")
    headline_zone = next(zone for zone in resolved["zones"] if zone["role"] == "headline")

    assert isinstance(logo_zone["x"], int)
    assert isinstance(logo_zone["width"], int)
    assert logo_zone["x"] == 810
    assert logo_zone["width"] == 238
    assert headline_zone["x"] == 108
    assert headline_zone["height"] == 108


def test_resolve_blueprint_payload_completes_symbolic_zone_map() -> None:
    stored = {
        "layout_type": "single-panel",
        "zones": [{"zone_id": "headline", "role": "headline"}],
        "hierarchy": ["headline"],
        "text_blocks": [{"role": "headline", "text": "Hello"}],
        "image_zones": [],
        "logo_rules": {},
        "cta_placement": {},
        "platform_preset": "instagram",
        "export_format": "png",
        "overflow_strategy": {"mode": "shrink_then_wrap"},
    }

    resolved = ContentService._resolve_blueprint_payload(
        stored_blueprint=stored,
        template_zone_map=None,
        override_blueprint=None,
        studio_panel={"platform_preset": "linkedin", "file_type": "pdf", "size": {"width": 1200, "height": 627}},
    )

    assert resolved["zones"][0]["role"] == "headline"
    assert resolved["zones"][0]["width"] > 0
    assert resolved["zones"][0]["height"] > 0


def test_resolve_scene_graph_payload_updates_canvas_to_export_panel() -> None:
    resolved = ContentService._resolve_scene_graph_payload(
        stored_scene_graph={
            "layout_mode": "synthesized_layout",
            "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
            "layers": ["background", "content"],
            "elements": [],
            "styles": {},
        },
        studio_panel={"platform_preset": "linkedin", "file_type": "pdf", "size": {"width": 1200, "height": 627}},
    )

    assert resolved is not None
    assert resolved["canvas"]["width"] == 1200
    assert resolved["canvas"]["height"] == 627
    assert resolved["canvas"]["platform"] == "linkedin"
    assert resolved["canvas"]["file_type"] == "pdf"


def test_supports_ai_final_render_export_for_ai_led_png_social_formats() -> None:
    assert ContentService._requires_ai_final_render_for_panel(
        {"format": "static", "file_type": "png"},
    ) is True
    assert ContentService._requires_ai_final_render_for_panel(
        {"format": "carousel", "file_type": "png"},
    ) is True
    assert ContentService._requires_ai_final_render_for_panel(
        {"format": "infographic", "file_type": "png"},
    ) is True
    assert ContentService._supports_ai_final_render_export(
        {"format": "static", "file_type": "png"},
        {"render_authority": "ai"},
    ) is True
    assert ContentService._supports_ai_final_render_export(
        {"format": "carousel", "file_type": "png"},
        {"render_authority": "ai"},
    ) is True
    assert ContentService._supports_ai_final_render_export(
        {"format": "infographic", "file_type": "png"},
        {"render_authority": "ai"},
    ) is True
    assert ContentService._supports_ai_final_render_export(
        {"format": "static", "file_type": "jpg"},
        {"render_authority": "ai"},
    ) is True
    assert ContentService._supports_ai_final_render_export(
        {"format": "static", "file_type": "pdf"},
        {"render_authority": "ai"},
    ) is True
    assert ContentService._supports_ai_final_render_export(
        {"format": "static", "file_type": "doc"},
        {"render_authority": "ai"},
    ) is True
    assert ContentService._supports_ai_final_render_export(
        {"format": "pdf", "file_type": "pdf"},
        {"render_authority": "ai"},
    ) is False


def test_effective_generate_image_requested_forces_ai_render_panels_on() -> None:
    assert ContentService._effective_generate_image_requested(
        studio_panel={"format": "carousel", "file_type": "png"},
        generate_image=False,
    ) is True
    assert ContentService._effective_generate_image_requested(
        studio_panel={"format": "static", "file_type": "png"},
        generate_image=None,
    ) is True
    assert ContentService._effective_generate_image_requested(
        studio_panel={"format": "pdf", "file_type": "pdf"},
        generate_image=False,
    ) is False


def test_knowledge_queries_for_visual_identity_include_channel_grounding_terms() -> None:
    queries = ContentService._knowledge_queries_for_channel(
        "Create a premium barbell strategy post for Instagram",
        "visual_identity",
    )

    assert "Create a premium barbell strategy post for Instagram" in queries
    assert any("brand visual identity palette typography iconography composition system" in query for query in queries)
    assert any("barbell" in query for query in queries if "brand visual identity" in query)


def test_merge_retrieval_results_dedupes_chunks_and_keeps_best_score() -> None:
    merged = ContentService._merge_retrieval_results(
        [
            [
                {"content": "First", "score": 0.42, "metadata": {"chunk_id": "chunk-1", "source_id": "asset-1"}},
                {"content": "Second", "score": 0.31, "metadata": {"chunk_id": "chunk-2", "source_id": "asset-2"}},
            ],
            [
                {"content": "First improved", "score": 0.18, "metadata": {"chunk_id": "chunk-1", "source_id": "asset-1"}},
                {"content": "Third", "score": 0.27, "metadata": {"chunk_id": "chunk-3", "source_id": "asset-3"}},
            ],
        ],
        limit=3,
    )

    assert [item["metadata"]["chunk_id"] for item in merged] == ["chunk-1", "chunk-3", "chunk-2"]
    assert merged[0]["content"] == "First improved"


def test_should_use_ai_final_render_overlay_when_exact_text_contract_exists() -> None:
    single_asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        content_version_id=uuid4(),
        asset_role="render_preview",
        mime_type="image/png",
        storage_path="tenant/brand/generated/final-render.png",
        width=1080,
        height=1080,
        metadata_json={
            "render_source": "ai",
            "generation_stage": "final_render",
            "render_overlay_text": {"headline": "Static headline", "body": "Static body", "cta": "Explore", "hashtags": [], "metadata": {}},
        },
    )
    carousel_asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        content_version_id=uuid4(),
        asset_role="render_preview",
        mime_type="image/png",
        storage_path="tenant/brand/generated/final-render-slide-1.png",
        width=1080,
        height=1080,
        metadata_json={
            "render_source": "ai",
            "generation_stage": "final_render",
            "render_overlay_text": {"headline": "Slide headline", "body": "Slide body", "cta": "Explore", "hashtags": [], "metadata": {}},
        },
    )

    assert ContentService._should_use_ai_final_render_overlay_for_panel(
        {"format": "static", "file_type": "png"},
        [single_asset],
    ) is False
    assert ContentService._should_use_ai_final_render_overlay_for_panel(
        {"format": "carousel", "file_type": "png"},
        [carousel_asset],
    ) is False

    carousel_overlay_asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        content_version_id=uuid4(),
        asset_role="render_preview",
        mime_type="image/png",
        storage_path="tenant/brand/generated/final-render-slide-2.png",
        width=1080,
        height=1080,
        metadata_json={
            "render_source": "ai",
            "generation_stage": "final_render",
            "render_overlay_scene_graph": {
                "canvas": {"width": 1080, "height": 1080, "platform": "linkedin"},
                "elements": [
                    {"element_id": "headline_text_slide_2", "element_type": "text", "role": "headline", "geometry": {"x": 0.08, "y": 0.1, "width": 0.6, "height": 0.16}},
                    {"element_id": "body_text_slide_2", "element_type": "text", "role": "body", "geometry": {"x": 0.08, "y": 0.3, "width": 0.52, "height": 0.2}},
                ],
            },
            "render_overlay_text": {"headline": "Slide headline", "body": "Slide body", "cta": "Explore", "hashtags": [], "metadata": {}},
        },
    )
    assert ContentService._should_use_ai_final_render_overlay_for_panel(
        {"format": "carousel", "file_type": "png"},
        [carousel_overlay_asset],
    ) is True


def test_sequence_pack_relevance_filter_rejects_irrelevant_family_for_prompt() -> None:
    sequence_pack = {
        "family_name": "FLOATING-RATE-BONDS",
        "selected_template_name": "Floating-Rate-Bonds-5",
        "slides": [
            {"slide_index": 1, "template_name": "Floating-Rate-Bonds-1"},
            {"slide_index": 2, "template_name": "Floating-Rate-Bonds-2"},
        ],
    }

    assert ContentService._sequence_pack_is_relevant_to_prompt(
        "Create a 5-slide carousel on retirement planning mistakes.",
        sequence_pack,
    ) is False
    assert ContentService._sequence_pack_is_relevant_to_prompt(
        "Create a 5-slide carousel on floating rate bond strategies.",
        sequence_pack,
    ) is True


def test_knowledge_channels_for_social_png_excludes_template_ocr() -> None:
    channels = ContentService._knowledge_channels_for_panel(
        {"platform_preset": "instagram", "format": "static", "file_type": "png"},
    )
    assert "template" not in channels
    assert "reference_creative" in channels


def test_knowledge_channels_for_pdf_keeps_template_knowledge() -> None:
    channels = ContentService._knowledge_channels_for_panel(
        {"platform_preset": "linkedin", "format": "pdf", "file_type": "pdf"},
    )
    assert "template" in channels


def test_find_ai_final_render_asset_prefers_tagged_render_preview() -> None:
    preferred_path = "tenant/brand/generated/final-render.png"
    assets = [
        GeneratedAsset(
            id=uuid4(),
            tenant_id=uuid4(),
            brand_space_id=uuid4(),
            content_version_id=uuid4(),
            asset_role="render_preview",
            mime_type="image/png",
            storage_path=preferred_path,
            width=1080,
            height=1080,
            metadata_json={"render_source": "ai", "generation_stage": "final_render"},
        ),
        GeneratedAsset(
            id=uuid4(),
            tenant_id=uuid4(),
            brand_space_id=uuid4(),
            content_version_id=uuid4(),
            asset_role="ai_image",
            mime_type="image/png",
            storage_path="tenant/brand/generated/hero.png",
            width=1080,
            height=1080,
            metadata_json={},
        ),
    ]

    resolved = ContentService._find_ai_final_render_asset(
        assets,
        explainability={
            "render_authority": "ai",
            "final_render_asset": {"storage_path": preferred_path},
        },
        studio_panel={"format": "static", "file_type": "png"},
    )

    assert resolved is not None
    assert resolved.storage_path == preferred_path


def test_find_ai_final_render_assets_preserves_slide_order_from_explainability() -> None:
    first_path = "tenant/brand/generated/final-render-slide-1.png"
    second_path = "tenant/brand/generated/final-render-slide-2.png"
    assets = [
        GeneratedAsset(
            id=uuid4(),
            tenant_id=uuid4(),
            brand_space_id=uuid4(),
            content_version_id=uuid4(),
            asset_role="render_export",
            mime_type="image/png",
            storage_path=second_path,
            width=1080,
            height=1080,
            metadata_json={"render_source": "ai", "generation_stage": "final_render", "slide_index": 2, "slide_count": 2},
        ),
        GeneratedAsset(
            id=uuid4(),
            tenant_id=uuid4(),
            brand_space_id=uuid4(),
            content_version_id=uuid4(),
            asset_role="render_preview",
            mime_type="image/png",
            storage_path=first_path,
            width=1080,
            height=1080,
            metadata_json={"render_source": "ai", "generation_stage": "final_render", "slide_index": 1, "slide_count": 2},
        ),
    ]

    resolved = ContentService._find_ai_final_render_assets(
        assets,
        explainability={
            "render_authority": "ai",
            "final_render_assets": [
                {"storage_path": first_path, "slide_index": 1},
                {"storage_path": second_path, "slide_index": 2},
            ],
        },
        studio_panel={"format": "carousel", "file_type": "png"},
    )

    assert [asset.storage_path for asset in resolved] == [first_path, second_path]


def test_should_render_missing_ai_final_assets_for_rewrite_when_child_has_no_assets() -> None:
    content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        parent_version_id=uuid4(),
        prompt="Rewrite this carousel with a different layout and tone.",
        generated_payload={},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )

    should_render = ContentService._should_render_missing_ai_final_assets_for_rewrite(
        content=content,
        ai_final_render_assets=[],
        explainability={
            "render_authority": "ai",
            "rewrite_source_content_version_id": str(uuid4()),
        },
        selective_regeneration_plan={
            "targeted_slide_indexes": [1, 2, 3, 4, 5],
            "rewrite_source_content_version_id": str(uuid4()),
            "only_targeted": True,
        },
    )

    assert should_render is True


def test_should_not_render_missing_ai_final_assets_without_targeted_rewrite_plan() -> None:
    content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        parent_version_id=uuid4(),
        prompt="Rewrite this carousel with a different layout and tone.",
        generated_payload={},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )

    should_render = ContentService._should_render_missing_ai_final_assets_for_rewrite(
        content=content,
        ai_final_render_assets=[],
        explainability={"render_authority": "ai"},
        selective_regeneration_plan={},
    )

    assert should_render is False


def test_template_metadata_payload_serializes_orm_template_metadata() -> None:
    template_meta = TemplateMetadata(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        template_id=uuid4(),
        zone_map={"zones": [{"zone_id": "headline"}]},
        sizing_rules={"width": 1200, "height": 627},
        platform_rules={"platforms": ["instagram"]},
        editable_fields=["headline", "body"],
        export_rules={"file_types": ["png"]},
    )

    payload = ContentService._template_metadata_payload(template_meta)

    assert payload == {
        "zone_map": {"zones": [{"zone_id": "headline"}]},
        "sizing_rules": {"width": 1200, "height": 627},
        "platform_rules": {"platforms": ["instagram"]},
        "editable_fields": ["headline", "body"],
        "export_rules": {"file_types": ["png"]},
    }


def test_knowledge_channels_include_uploaded_reference_inputs() -> None:
    channels = ContentService._knowledge_channels()
    assert "reference_creative" in channels
    assert "mood_board" in channels
    assert "visual_identity" in channels
    assert "chat_reference" in channels


def test_build_template_context_payload_derives_sequence_pack_from_reference_creative_family() -> None:
    template_meta = TemplateMetadata(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        template_id=uuid4(),
        zone_map={"layout_type": "template", "zones": [{"zone_id": "headline", "role": "headline"}]},
        sizing_rules={"width": 1080, "height": 1350},
        platform_rules={},
        editable_fields=["headline", "body"],
        export_rules={"file_types": ["png"]},
    )

    payload = ContentService._build_template_context_payload(
        template_meta=template_meta,
        selected_template_id=str(template_meta.template_id),
        selected_template_name="TOP-MISTAKES-1",
        template_recommendations=[
            {"template_id": str(uuid4()), "name": "TOP-MISTAKES-1", "metadata": {"editable_fields": ["headline", "body"]}},
            {"template_id": str(uuid4()), "name": "TOP-MISTAKES-2", "metadata": {"editable_fields": ["headline", "body"]}},
            {"template_id": str(uuid4()), "name": "TOP-MISTAKES-3", "metadata": {"editable_fields": ["headline", "body", "cta"]}},
        ],
        reference_assets=[
            {"asset_role": "reference_creative", "storage_path": "tenant/reference_creatives/TOP-MISTAKES-3-abcdef123456.jpg"},
            {"asset_role": "reference_creative", "storage_path": "tenant/reference_creatives/TOP-MISTAKES-1-abcdef123456.jpg"},
            {"asset_role": "reference_creative", "storage_path": "tenant/reference_creatives/TOP-MISTAKES-2-abcdef123456.jpg"},
        ],
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
    )

    assert payload is not None
    assert payload["layout_type"] == "template"
    assert payload["sequence_pack"]["family_name"] == "TOP-MISTAKES"
    assert payload["sequence_pack"]["surface_policy"] == "style_reference_only"
    assert payload["sequence_pack"]["sequence_kind"] == "reference_driven_structural_blueprint"
    assert payload["sequence_pack"]["slide_count"] == 3
    assert [slide["slide_index"] for slide in payload["sequence_pack"]["slides"]] == [1, 2, 3]
    assert payload["sequence_pack"]["slides"][0]["reference_asset_path"].endswith("TOP-MISTAKES-1-abcdef123456.jpg")
    assert payload["sequence_pack"]["slides"][0]["story_role"] == "hook"
    assert payload["sequence_pack"]["slides"][1]["story_role"] == "structure"
    assert payload["sequence_pack"]["slides"][2]["story_role"] == "takeaway"
    assert payload["sequence_pack"]["slides"][0]["structural_cues"]
    assert payload["sequence_pack"]["sequence_cues"]


def test_build_template_context_payload_uses_reference_slide_zone_maps_and_rich_headline_hints() -> None:
    template_meta = TemplateMetadata(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        template_id=uuid4(),
        zone_map={"layout_type": "template", "zones": [{"zone_id": "headline", "role": "headline"}]},
        sizing_rules={"width": 1080, "height": 1350},
        platform_rules={},
        editable_fields=["headline", "body"],
        export_rules={"file_types": ["png"]},
    )

    payload = ContentService._build_template_context_payload(
        template_meta=template_meta,
        selected_template_id=str(template_meta.template_id),
        selected_template_name="TOP-MISTAKES-1",
        template_recommendations=[
            {"template_id": str(uuid4()), "name": "TOP-MISTAKES-1", "metadata": {"editable_fields": ["headline", "body"]}},
            {"template_id": str(uuid4()), "name": "TOP-MISTAKES-2", "metadata": {"editable_fields": ["headline", "body"]}},
            {"template_id": str(uuid4()), "name": "TOP-MISTAKES-3", "metadata": {"editable_fields": ["headline", "body", "cta"]}},
        ],
        reference_assets=[
            {
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference_creatives/TOP-MISTAKES-1-abcdef123456.jpg",
                "metadata": {
                    "heading": "Mistake 1: Chasing yield blindly",
                    "summary": "This should not be used because the heading is stronger.",
                    "zone_map": {
                        "layout_type": "editorial_split",
                        "zones": [
                            {"role": "headline", "x": 0.06, "y": 0.08, "w": 0.56, "h": 0.14},
                            {"role": "body", "x": 0.06, "y": 0.26, "w": 0.36, "h": 0.3},
                            {"role": "image", "x": 0.58, "y": 0.62, "w": 0.28, "h": 0.22},
                        ],
                    },
                },
            },
            {"asset_role": "reference_creative", "storage_path": "tenant/reference_creatives/TOP-MISTAKES-2-abcdef123456.jpg"},
            {"asset_role": "reference_creative", "storage_path": "tenant/reference_creatives/TOP-MISTAKES-3-abcdef123456.jpg"},
        ],
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
    )

    assert payload is not None
    first_slide = payload["sequence_pack"]["slides"][0]
    assert first_slide["headline_hint"] == "Mistake 1: Chasing yield blindly"
    assert first_slide["zone_map"]["layout_type"] == "editorial_split"
    assert first_slide["zone_map"]["zones"][2]["role"] == "image"


def test_build_template_context_payload_derives_sequence_pack_from_reference_metadata_blueprint() -> None:
    template_meta = TemplateMetadata(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        template_id=uuid4(),
        zone_map={"layout_type": "template", "zones": [{"zone_id": "headline", "role": "headline"}]},
        sizing_rules={"width": 1080, "height": 1350},
        platform_rules={},
        editable_fields=["headline", "body"],
        export_rules={"file_types": ["pdf"]},
    )

    payload = ContentService._build_template_context_payload(
        template_meta=template_meta,
        selected_template_id=None,
        selected_template_name=None,
        template_recommendations=[],
        reference_assets=[
            {
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference_creatives/fta-sample.pdf",
                "metadata": {
                    "label": "FTA sample",
                    "format": "carousel",
                    "page_count": 4,
                    "narrative_pattern": "hook_to_implication_sequence",
                    "structural_cues": [
                        "cover hook",
                        "what actually changed",
                        "what most coverage missed",
                        "implication close",
                    ],
                    "sequence_summary": "Analytical sequence moving from the overlooked headline into strategic implication.",
                    "summary": "Use an editorial close instead of a generic CTA page.",
                },
            }
        ],
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
    )

    assert payload is not None
    assert payload["sequence_pack"]["sequence_kind"] == "hook_to_implication_sequence"
    assert payload["sequence_pack"]["slide_count"] == 4
    assert [slide["slide_index"] for slide in payload["sequence_pack"]["slides"]] == [1, 2, 3, 4]
    assert [slide["story_role"] for slide in payload["sequence_pack"]["slides"]] == [
        "hook",
        "structure",
        "undercovered_angle",
        "strategic_meaning",
    ]
    assert payload["sequence_pack"]["slides"][0]["headline_hint"] == "Why this matters now"
    assert payload["sequence_pack"]["slides"][2]["headline_hint"] == "What most coverage missed"
    assert payload["sequence_pack"]["slides"][3]["sequence_summary"].startswith("Analytical sequence")


def test_build_template_context_payload_prefers_selected_template_explicit_sequence_pack_over_unrelated_family() -> None:
    payload = ContentService._build_template_context_payload(
        template_meta=SimpleNamespace(
            zone_map={},
            sizing_rules={},
            platform_rules={},
            editable_fields=["headline", "body"],
            export_rules={},
        ),
        selected_template_id="selected-template-id",
        selected_template_name="06.01.2026",
        template_recommendations=[
            {
                "template_id": "selected-template-id",
                "name": "06.01.2026",
                "metadata": {
                    "family_name": "FTA-ANALYSIS",
                    "sequence_blueprint": {
                        "family_name": "FTA-ANALYSIS",
                        "sequence_kind": "hook_to_implication_sequence",
                        "slides": [
                            {"slide_index": 1, "template_name": "06.01.2026", "headline": "Hook"},
                            {"slide_index": 2, "template_name": "06.01.2026", "headline": "Change"},
                            {"slide_index": 3, "template_name": "06.01.2026", "headline": "Implication"},
                        ],
                    },
                },
            },
            {
                "template_id": "other-template-id",
                "name": "FLOATING-RATE-BONDS-1",
                "metadata": {"label": "Floating Rate Bonds 1"},
            },
            {
                "template_id": "other-template-id-2",
                "name": "FLOATING-RATE-BONDS-2",
                "metadata": {"label": "Floating Rate Bonds 2"},
            },
            {
                "template_id": "other-template-id-3",
                "name": "FLOATING-RATE-BONDS-3",
                "metadata": {"label": "Floating Rate Bonds 3"},
            },
        ],
        reference_assets=[],
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
    )

    assert payload is not None
    assert payload["sequence_pack"]["family_name"] == "FTA-ANALYSIS"
    assert payload["sequence_pack"]["selected_template_id"] == "selected-template-id"
    assert [slide["template_name"] for slide in payload["sequence_pack"]["slides"]] == [
        "06.01.2026",
        "06.01.2026",
        "06.01.2026",
    ]


def test_build_template_context_payload_keeps_selected_template_authority_when_unrelated_family_has_richer_sequence_metadata() -> None:
    payload = ContentService._build_template_context_payload(
        prompt="Create a 5-slide LinkedIn carousel on retirement planning mistakes.",
        template_meta=SimpleNamespace(
            zone_map={"layout_type": "template", "zones": [{"zone_id": "headline", "role": "headline"}]},
            sizing_rules={},
            platform_rules={},
            editable_fields=["headline", "body", "image", "cta"],
            export_rules={},
        ),
        selected_template_id="selected-template-id",
        selected_template_name="06.01.2026",
        template_recommendations=[
            {
                "template_id": "selected-template-id",
                "name": "06.01.2026",
                "metadata": {
                    "label": "Planning your retirement",
                    "page_count": 1,
                    "summary": "Premium retirement planning explainer for Jiraaf.",
                },
            },
            {
                "template_id": "other-template-id",
                "name": "FLOATING-RATE-BONDS-1",
                "metadata": {"label": "Floating Rate Bonds 1"},
            },
            {
                "template_id": "other-template-id-2",
                "name": "FLOATING-RATE-BONDS-2",
                "metadata": {"label": "Floating Rate Bonds 2"},
            },
            {
                "template_id": "other-template-id-3",
                "name": "FLOATING-RATE-BONDS-3",
                "metadata": {"label": "Floating Rate Bonds 3"},
            },
        ],
        reference_assets=[
            {
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference_creatives/Floating-Rate-Bonds-1-abcdef123456.jpg",
                "metadata": {
                    "label": "Floating Rate Bonds 1",
                    "page_count": 5,
                    "structural_cues": [
                        "cover hook",
                        "what happened",
                        "undercovered angle",
                        "why it matters",
                        "takeaway close",
                    ],
                },
            },
            {
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference_creatives/06.01.2026-23cb35b925de4a76aa1219e78891b125.png",
                "metadata": {
                    "label": "Planning your retirement",
                    "page_count": 1,
                    "summary": "Selected retirement reference from Jiraaf brandspace.",
                },
            },
        ],
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
    )

    assert payload is not None
    assert payload["sequence_pack"]["selected_template_id"] == "selected-template-id"
    assert payload["sequence_pack"]["selected_template_name"] == "06.01.2026"
    assert payload["sequence_pack"]["slide_count"] == 5
    assert all(slide["template_name"] == "06.01.2026" for slide in payload["sequence_pack"]["slides"])
    assert payload["sequence_pack"]["family_name"] != "FLOATING-RATE-BONDS"


def test_build_template_context_payload_keeps_selected_template_authority_pack_even_when_prompt_topic_differs_from_template_title() -> None:
    payload = ContentService._build_template_context_payload(
        prompt="Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement signed on 27 April 2026.",
        template_meta=SimpleNamespace(
            zone_map={"layout_type": "template", "zones": [{"zone_id": "headline", "role": "headline"}]},
            sizing_rules={},
            platform_rules={},
            editable_fields=["headline", "body", "image"],
            export_rules={},
        ),
        selected_template_id="selected-template-id",
        selected_template_name="Behavioural Biases",
        template_recommendations=[
            {
                "template_id": "selected-template-id",
                "name": "Behavioural Biases",
                "asset_url": "tenant/reference/Behavioural-Biases.pdf",
                "metadata": {
                    "page_count": 7,
                    "format_family": "carousel",
                    "summary": "Investor bias explainer with a 7-slide paginated structure.",
                },
            }
        ],
        reference_assets=[
            {
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference/FTA-3.pdf",
                "mime_type": "application/pdf",
                "metadata": {
                    "format_family": "carousel",
                    "sequence_family": "FTA",
                    "reference_slide_index": 3,
                    "summary": "NZ opened 100% of tariff lines and relaxed mobility caps for Indian students.",
                },
            }
        ],
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
    )

    assert payload is not None
    assert payload["sequence_pack"]["selected_template_id"] == "selected-template-id"
    assert payload["sequence_pack"]["selected_template_name"] == "Behavioural Biases"
    assert payload["sequence_pack"]["slide_count"] == 7
    assert all(slide["template_name"] == "Behavioural Biases" for slide in payload["sequence_pack"]["slides"])


def test_build_template_context_payload_prefers_carousel_capable_references_over_single_page_static_samples() -> None:
    payload = ContentService._build_template_context_payload(
        prompt="Create a 5-slide LinkedIn carousel on retirement planning mistakes.",
        template_meta=SimpleNamespace(
            zone_map={"layout_type": "template", "zones": [{"zone_id": "headline", "role": "headline"}]},
            sizing_rules={},
            platform_rules={},
            editable_fields=["headline", "body", "image"],
            export_rules={},
        ),
        selected_template_id=None,
        selected_template_name=None,
        template_recommendations=[
            {
                "template_id": "frb-1",
                "name": "Floating-Rate-Bonds-1",
                "metadata": {"label": "Floating Rate Bonds 1", "page_count": 1},
            },
            {
                "template_id": "frb-2",
                "name": "Floating-Rate-Bonds-2",
                "metadata": {"label": "Floating Rate Bonds 2", "page_count": 1},
            },
            {
                "template_id": "frb-3",
                "name": "Floating-Rate-Bonds-3",
                "metadata": {"label": "Floating Rate Bonds 3", "page_count": 1},
            },
        ],
        reference_assets=[
            {
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference_creatives/Retirement-Arc-1-sample.pdf",
                "metadata": {
                    "label": "Retirement Arc",
                    "family_name": "RETIREMENT-ARC",
                    "page_count": 5,
                    "structural_cues": [
                        "cover hook",
                        "mistake setup",
                        "what it costs",
                        "what to do instead",
                        "takeaway close",
                    ],
                    "summary": "Retirement planning carousel with slide-by-slide storytelling.",
                },
            },
            {
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference_creatives/Floating-Rate-Bonds-1-sample.jpg",
                "metadata": {"label": "Floating Rate Bonds 1", "page_count": 1},
            },
        ],
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
    )

    assert payload is not None
    assert payload["sequence_pack"]["family_name"] == "RETIREMENT-ARC"
    assert payload["sequence_pack"]["slide_count"] == 5
    assert payload["sequence_pack"]["slides"][0]["reference_asset_path"].endswith(".pdf")
    assert all(
        "FLOATING-RATE-BONDS" not in str(slide.get("template_name") or "")
        for slide in payload["sequence_pack"]["slides"]
    )


def test_build_selected_template_authority_sequence_pack_uses_matching_asset_page_count_when_available() -> None:
    sequence_pack = ContentService._build_selected_template_authority_sequence_pack(
        selected_template_id="selected-template-id",
        selected_template_name="Retirement-Planning-1",
        normalized_recommendations=[
            {
                "template_id": "selected-template-id",
                "name": "Retirement-Planning-1",
                "metadata": {"summary": "Retirement journey in four steps."},
            }
        ],
        reference_assets=[
            {
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference_creatives/Retirement-Planning-1-abcdef123456.pdf",
                "metadata": {
                    "page_count": 4,
                    "structural_cues": [
                        "cover hook",
                        "what to assess",
                        "goal math",
                        "takeaway close",
                    ],
                },
            }
        ],
        fallback_editable_fields=["headline", "body"],
        base_zone_map={"zones": [{"zone_id": "headline", "role": "headline"}]},
    )

    assert sequence_pack is not None
    assert sequence_pack["slide_count"] == 4
    assert sequence_pack["selected_template_id"] == "selected-template-id"
    assert sequence_pack["selected_template_name"] == "Retirement-Planning-1"
    assert [slide["story_role"] for slide in sequence_pack["slides"]] == [
        "hook",
        "structure",
        "strategic_meaning",
        "takeaway",
    ]


def test_selected_template_authority_sequence_pack_uses_pdf_page_editorial_copy() -> None:
    pdf_path = Path.cwd() / f"violyt-selected-template-{uuid4().hex}.pdf"
    try:
        canvas = pdf_canvas.Canvas(str(pdf_path))
        for lines in (
            [
                "India closed its fastest trade deal ever",
                "with New Zealand.",
                "Here is what you missed.",
            ],
            [
                "What's actually in the deal:",
                "Zero duty on Indian exports across all tariff lines.",
                "Top gainers: textiles, pharma, engineering.",
            ],
            [
                "What most coverage missed.",
                "Three things worth noticing.",
                "The deal is not equal on paper, and it was not meant to be.",
            ],
            [
                "Small deal. Bigger shape.",
                "The clauses negotiated here set a template for bigger trade deals.",
            ],
        ):
            y = 760
            for line in lines:
                canvas.drawString(72, y, line)
                y -= 28
            canvas.drawString(72, 40, "Disclaimer: Fixed returns do not constitute guaranteed returns.")
            canvas.showPage()
        canvas.save()

        class _FakeStorage:
            def exists(self, storage_path: str) -> bool:
                return storage_path == "tenant/reference_creatives/FTA-3.pdf"

            def absolute_path(self, storage_path: str) -> str:
                assert storage_path == "tenant/reference_creatives/FTA-3.pdf"
                return str(pdf_path)

        sequence_pack = ContentService._build_selected_template_authority_sequence_pack(
            selected_template_id="selected-template-id",
            selected_template_name="FTA (3)",
            normalized_recommendations=[
                {
                    "template_id": "selected-template-id",
                    "name": "FTA (3)",
                    "metadata": {"summary": "Layout marketing_social. Editable zones: headline, body, image."},
                }
            ],
            reference_assets=[
                {
                    "asset_role": "reference_creative",
                    "storage_path": "tenant/reference_creatives/FTA-3.pdf",
                    "mime_type": "application/pdf",
                    "metadata": {"page_count": 4, "summary": "Generic carousel summary"},
                }
            ],
            fallback_editable_fields=["headline", "body"],
            base_zone_map={"zones": [{"zone_id": "headline", "role": "headline"}]},
            storage=_FakeStorage(),
        )

        assert sequence_pack is not None
        assert sequence_pack["slide_count"] == 4
        assert sequence_pack["slides"][0]["headline_hint"] == "India closed its fastest trade deal ever with New Zealand"
        assert sequence_pack["slides"][0]["sample_page_supporting"] == "Here is what you missed."
        assert "Disclaimer" not in sequence_pack["slides"][0]["sample_page_copy"]
        assert sequence_pack["slides"][2]["headline_hint"] == "What most coverage missed"
        assert sequence_pack["slides"][2]["story_role"] == "undercovered_angle"
        assert sequence_pack["slides"][2]["sample_page_copy_behavior"] == "curiosity_gap"
        assert sequence_pack["slides"][2]["sample_page_editorial_role"] == "undercovered_angle"
        assert sequence_pack["slides"][3]["headline_hint"] == "Small deal. Bigger shape"
        assert sequence_pack["slides"][3]["sample_page_closing_grammar"] == "macro_takeaway"
        assert sequence_pack["slides"][3]["sample_page_copy_behavior"] == "strategic_signal"
        assert sequence_pack["slides"][3]["sample_page_editorial_source"] == "pdf_text_blocks"
    finally:
        try:
            pdf_path.unlink(missing_ok=True)
        except OSError:
            pass


def test_build_selected_template_authority_sequence_pack_fills_paths_summaries_and_sanitizes_zero_zones() -> None:
    sequence_pack = ContentService._build_selected_template_authority_sequence_pack(
        selected_template_id="selected-template-id",
        selected_template_name="06.01.2026",
        normalized_recommendations=[
            {
                "template_id": "selected-template-id",
                "name": "06.01.2026",
                "storage_path": "tenant/reference_creatives/06.01.2026-abcdef123456.png",
                "metadata": {
                    "label": "Planning your retirement",
                    "summary": "Layout infographic. Background flat. Editable zones: headline, body, image, logo.",
                    "heading": "Go beyond the headline",
                },
            }
        ],
        reference_assets=[],
        fallback_editable_fields=["headline", "body", "image", "cta"],
        base_zone_map={
            "layout_type": "infographic",
            "zones": [
                {"role": "logo", "x": 0.88, "y": 0.02, "w": 0.1, "h": 0.08},
                {"role": "headline", "x": 0.05, "y": 0.1, "w": 0.65, "h": 0.12},
                {"role": "body", "x": 0.05, "y": 0.23, "w": 0.7, "h": 0.06},
                {"role": "image", "x": 0.55, "y": 0.75, "w": 0.4, "h": 0.2},
                {"role": "cta", "x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
            ],
        },
    )

    assert sequence_pack is not None
    first_slide = sequence_pack["slides"][0]
    assert first_slide["template_asset_path"] == "tenant/reference_creatives/06.01.2026-abcdef123456.png"
    assert first_slide["reference_asset_path"] == "tenant/reference_creatives/06.01.2026-abcdef123456.png"
    assert first_slide["sequence_summary"] == "Go beyond the headline"
    assert all(
        float(zone.get("w") or 0) > 0 and float(zone.get("h") or 0) > 0
        for zone in first_slide["zone_map"]["zones"]
    )
    assert all(str(zone.get("role") or "").strip().lower() != "cta" for zone in first_slide["zone_map"]["zones"])


def test_build_selected_template_authority_sequence_pack_ignores_numeric_template_name_as_headline_hint() -> None:
    sequence_pack = ContentService._build_selected_template_authority_sequence_pack(
        selected_template_id="selected-template-id",
        selected_template_name="06.01.2026",
        normalized_recommendations=[
            {
                "template_id": "selected-template-id",
                "name": "06.01.2026",
                "metadata": {
                    "summary": "Layout infographic. Background flat. Editable zones: headline, body, image, logo.",
                },
            }
        ],
        reference_assets=[],
        fallback_editable_fields=["headline", "body", "image", "cta"],
        base_zone_map={"layout_type": "infographic", "zones": [{"role": "headline", "x": 0.05, "y": 0.1, "w": 0.65, "h": 0.12}]},
    )

    assert sequence_pack is not None
    assert sequence_pack["slides"][0]["headline_hint"] == "Why this matters now"
    assert sequence_pack["slides"][1]["headline_hint"] == "What actually changed"
    assert sequence_pack["slides"][0]["sequence_summary"] == "Why this matters now"


def test_build_reference_metadata_sequence_pack_derives_blueprint_from_pdf_pages() -> None:
    pdf_path = Path.cwd() / f"violyt-sequence-pack-{uuid4().hex}.pdf"
    try:
        canvas = pdf_canvas.Canvas(str(pdf_path))
        for lines in (
            [
                "India closed its fastest trade deal ever.",
                "Here is what most people missed about the opening move.",
            ],
            [
                "What actually changed",
                "Tariff cuts landed alongside mobility concessions and services access.",
            ],
            [
                "What most coverage missed",
                "The accountability clause creates asymmetry once benchmarks slip.",
            ],
            [
                "Small deal. Bigger shape.",
                "This is the template for how future strategic trade concessions may be sequenced.",
            ],
        ):
            y = 760
            for line in lines:
                canvas.drawString(72, y, line)
                y -= 28
            canvas.showPage()
        canvas.save()

        class _FakeStorage:
            def exists(self, storage_path: str) -> bool:
                return storage_path == "tenant/reference_creatives/fta-reference.pdf"

            def absolute_path(self, storage_path: str) -> str:
                assert storage_path == "tenant/reference_creatives/fta-reference.pdf"
                return str(pdf_path)

        sequence_pack = ContentService._build_reference_metadata_sequence_pack(
            selected_template_id=None,
            selected_template_name=None,
            normalized_recommendations=[],
            reference_assets=[
                {
                    "asset_role": "reference_creative",
                    "storage_path": "tenant/reference_creatives/fta-reference.pdf",
                    "mime_type": "application/pdf",
                    "metadata": {
                        "label": "FTA sample",
                        "format": "carousel",
                        "summary": "Use an editorial close instead of a generic CTA page.",
                    },
                }
            ],
            fallback_editable_fields=["headline", "body"],
            storage=_FakeStorage(),
        )

        assert sequence_pack is not None
        assert sequence_pack["sequence_kind"] == "reference_pdf_blueprint"
        assert sequence_pack["slide_count"] == 4
        assert [slide["story_role"] for slide in sequence_pack["slides"]] == [
            "hook",
            "structure",
            "undercovered_angle",
            "strategic_meaning",
        ]
        assert sequence_pack["slides"][0]["headline_hint"] == "India closed its fastest trade deal ever"
        assert sequence_pack["slides"][2]["headline_hint"] == "What most coverage missed"
        assert sequence_pack["slides"][3]["sequence_summary"].startswith("Small deal. Bigger shape.")
    finally:
        try:
            pdf_path.unlink(missing_ok=True)
        except OSError:
            pass


def test_knowledge_asset_payload_preserves_asset_role_from_metadata() -> None:
    asset = KnowledgeAsset(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        name="Mood board",
        original_filename="mood-board.pdf",
        mime_type="application/pdf",
        storage_path="tenant/brand/uploads/mood-board.pdf",
        lifecycle_state="indexed",
        channel="mood_board",
        page_count=2,
        metadata_json={"asset_role": "reference_creative", "section": "visual_identity"},
        structured_data_json={"sequence_summary": "Lead with a hook before the explanation."},
        normalized_data_json={"structural_cues": ["cover hook", "detail explanation"]},
        validation_state="clean",
    )

    payload = ContentService._knowledge_asset_payload(asset)

    assert payload["asset_id"] == str(asset.id)
    assert payload["asset_role"] == "reference_creative"
    assert payload["mime_type"] == "application/pdf"
    assert payload["storage_path"] == "tenant/brand/uploads/mood-board.pdf"
    assert payload["metadata"]["asset_role"] == "reference_creative"
    assert payload["metadata"]["section"] == "visual_identity"
    assert payload["metadata"]["page_count"] == 2
    assert payload["metadata"]["sequence_summary"] == "Lead with a hook before the explanation."
    assert payload["metadata"]["structural_cues"] == ["cover hook", "detail explanation"]
    assert payload["validation_state"] == "clean"
    assert payload["trust_level"] == "trusted"


def test_knowledge_asset_payload_enriches_reference_format_family_and_sequence_signature() -> None:
    asset = KnowledgeAsset(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        name="Floating Rate Bonds 5",
        original_filename="Floating-Rate-Bonds-5.png",
        mime_type="image/png",
        storage_path="tenant/brand/reference/Floating-Rate-Bonds-5-abcd1234.png",
        lifecycle_state="indexed",
        channel="reference_creative",
        page_count=1,
        metadata_json={
            "asset_role": "reference_creative",
            "summary": "Layout marketing_social. Background flat. Editable zones: headline, logo, image, body.",
        },
        structured_data_json={},
        normalized_data_json={},
        validation_state="clean",
    )

    payload = ContentService._knowledge_asset_payload(asset)

    assert payload["format_family"] == "carousel"
    assert payload["metadata"]["format_family"] == "carousel"
    assert payload["metadata"]["sequence_family"] == "FLOATING-RATE-BONDS"
    assert payload["metadata"]["reference_slide_index"] == 5


def test_filter_reference_assets_for_studio_format_prefers_enriched_carousel_assets() -> None:
    assets = [
        {
            "asset_id": str(uuid4()),
            "asset_role": "reference_creative",
            "mime_type": "image/png",
            "storage_path": "tenant/reference/WhatsApp-Image-2026-04-21.jpeg",
            "metadata": {
                "summary": "Layout infographic. Background flat. Editable zones: logo, headline, body, image.",
                "page_count": 1,
            },
        },
        {
            "asset_id": str(uuid4()),
            "asset_role": "reference_creative",
            "mime_type": "image/png",
            "storage_path": "tenant/reference/Floating-Rate-Bonds-5-abcd1234.png",
            "metadata": {
                "summary": "Layout marketing_social. Background flat. Editable zones: headline, logo, image, body.",
                "page_count": 1,
            },
        },
        {
            "asset_id": str(uuid4()),
            "asset_role": "reference_creative",
            "mime_type": "application/pdf",
            "storage_path": "tenant/reference/Bond-Analyzer.pdf",
            "metadata": {
                "summary": "Bond market explainer carousel.",
                "page_count": 5,
            },
        },
    ]

    filtered = ContentService._filter_reference_assets_for_studio_format(
        assets,
        studio_panel={"format": "carousel"},
    )

    assert filtered
    assert all(str(item.get("format_family") or "") == "carousel" for item in filtered)
    assert not any("WhatsApp-Image" in str(item.get("storage_path") or "") for item in filtered)


def test_selected_reference_visual_assets_materializes_trace_assets_for_export() -> None:
    assets = ContentService._selected_reference_visual_assets(
        {
            "selected_reference_images": [
                {
                    "asset_id": str(uuid4()),
                    "asset_role": "reference_creative",
                    "mime_type": "image/png",
                    "storage_path": "tenant/brand/reference/hero-1.png",
                    "width": 1080,
                    "height": 1080,
                    "metadata": {"label": "Airport traveler"},
                    "trust_level": "trusted",
                },
                {
                    "asset_id": str(uuid4()),
                    "asset_role": "reference_creative",
                    "mime_type": "image/png",
                    "storage_path": "tenant/brand/reference/hero-1.png",
                    "width": 1080,
                    "height": 1080,
                    "metadata": {"label": "Duplicate path"},
                    "trust_level": "trusted",
                },
            ]
        }
    )

    assert len(assets) == 1
    assert assets[0].storage_path == "tenant/brand/reference/hero-1.png"
    assert assets[0].asset_role == "reference_creative"


def test_selected_reference_visual_assets_skips_literal_reference_surface_when_rendering_synthesized_layout() -> None:
    assets = ContentService._selected_reference_visual_assets(
        {
            "selected_reference_images": [
                {
                    "asset_id": str(uuid4()),
                    "asset_role": "reference_creative",
                    "mime_type": "image/png",
                    "storage_path": "tenant/brand/reference/off-topic-chart.png",
                    "width": 1080,
                    "height": 1080,
                    "metadata": {"label": "foreign investment chart"},
                    "trust_level": "trusted",
                },
                {
                    "asset_id": str(uuid4()),
                    "asset_role": "icon",
                    "mime_type": "image/png",
                    "storage_path": "tenant/brand/reference/coin-icon.png",
                    "width": 256,
                    "height": 256,
                    "metadata": {"label": "coin icon"},
                    "trust_level": "trusted",
                },
            ]
        },
        allow_literal_reference_surfaces=False,
    )

    assert len(assets) == 1
    assert assets[0].storage_path == "tenant/brand/reference/coin-icon.png"
    assert assets[0].asset_role == "icon"


def test_sanitize_scene_graph_for_structured_render_removes_literal_reference_bindings() -> None:
    scene_graph = {
        "layout_mode": "synthesized_layout",
        "template_adaptation": {"reference_style_only": True},
        "assets": [
            {"asset_role": "reference_creative", "storage_path": "tenant/brand/reference/off-topic-chart.png"},
            {"asset_role": "icon", "storage_path": "tenant/brand/reference/coin-icon.png"},
        ],
        "elements": [
            {
                "element_id": "image",
                "role": "image",
                "asset": {"asset_role": "reference_creative", "storage_path": "tenant/brand/reference/off-topic-chart.png"},
            },
            {
                "element_id": "icon",
                "role": "icon",
                "asset": {"asset_role": "icon", "storage_path": "tenant/brand/reference/coin-icon.png"},
            },
        ],
    }

    sanitized = ContentService._sanitize_scene_graph_for_structured_render(
        scene_graph,
        filter_literal_reference_surfaces=True,
    )

    assert sanitized is not None
    assert sanitized["assets"] == [{"asset_role": "icon", "storage_path": "tenant/brand/reference/coin-icon.png"}]
    assert "asset" not in sanitized["elements"][0]
    assert sanitized["elements"][1]["asset"]["storage_path"] == "tenant/brand/reference/coin-icon.png"


def test_filter_brand_reference_assets_for_prompt_removes_off_topic_campaign_assets() -> None:
    assets = [
        {
            "asset_id": str(uuid4()),
            "asset_role": "icon",
            "storage_path": "tenant/brand/assets/fd-to-bonds-03-icon.png",
            "metadata": {"label": "FD to bonds 03 icon set"},
            "trust_level": "trusted",
        },
        {
            "asset_id": str(uuid4()),
            "asset_role": "reference_creative",
            "storage_path": "tenant/brand/assets/travel-fares-moodboard.png",
            "metadata": {"label": "travel fares mood board"},
            "trust_level": "trusted",
        },
        {
            "asset_id": str(uuid4()),
            "asset_role": "reference_creative",
            "storage_path": "tenant/brand/assets/IMG_3022.png",
            "metadata": {"label": "IMG_3022"},
            "trust_level": "trusted",
        },
    ]

    filtered = ContentService._filter_brand_reference_assets_for_prompt(
        assets,
        prompt="Create an engaging Instagram post that shares tips and strategies to book flights at a lower cost",
        follow_up_mode="new_content",
    )

    assert len(filtered) == 2
    assert all("fd-to-bonds" not in str(asset["storage_path"]) for asset in filtered)


def test_filter_template_recommendations_for_prompt_drops_off_topic_named_templates() -> None:
    recommendations = [
        {"name": "FD to bonds-04", "reasons": ["keyword overlap: and, lower, post"], "metadata": {"tags": ["financial services"]}},
        {"name": "IMG_3022", "reasons": ["supports platform instagram"], "metadata": {"tags": ["headline", "image"]}},
        {"name": "Travel fares editorial", "reasons": ["travel hero"], "metadata": {"tags": ["travel", "booking"]}},
    ]

    filtered = ContentService._filter_template_recommendations_for_prompt(
        recommendations,
        prompt="Create an engaging Instagram post that shares tips and strategies to book flights at a lower cost",
        follow_up_mode="new_content",
        studio_panel={"format": "static"},
    )

    names = [str(item["name"]) for item in filtered]

    assert "FD to bonds-04" not in names
    assert "IMG_3022" in names
    assert "Travel fares editorial" in names


def test_filter_template_recommendations_for_prompt_prefers_static_family_for_static_generation() -> None:
    recommendations = [
        {"name": "Static hero", "score": 8.5, "metadata": {"format_family": "static", "adaptation_score": 18.5}},
        {"name": "Carousel story", "score": 9.9, "metadata": {"format_family": "carousel", "adaptation_score": 9.9}},
        {"name": "Infographic board", "score": 9.2, "metadata": {"format_family": "infographic", "adaptation_score": 9.2}},
    ]

    filtered = ContentService._filter_template_recommendations_for_prompt(
        recommendations,
        prompt="Create a static LinkedIn post about retirement planning mistakes",
        follow_up_mode="new_content",
        studio_panel={"format": "static"},
    )

    assert [item["name"] for item in filtered] == ["Static hero"]


def test_filter_template_recommendations_for_prompt_prefers_infographic_family_for_infographic_generation() -> None:
    recommendations = [
        {"name": "Infographic board", "score": 8.4, "metadata": {"format_family": "infographic", "adaptation_score": 18.4}},
        {"name": "Static card", "score": 9.5, "metadata": {"format_family": "static", "adaptation_score": 9.5}},
        {"name": "Carousel story", "score": 9.6, "metadata": {"format_family": "carousel", "adaptation_score": 9.6}},
    ]

    filtered = ContentService._filter_template_recommendations_for_prompt(
        recommendations,
        prompt="Create an infographic on retirement planning mistakes",
        follow_up_mode="new_content",
        studio_panel={"format": "infographic"},
    )

    assert [item["name"] for item in filtered] == ["Infographic board"]


def test_filter_template_recommendations_for_prompt_prefers_carousel_family_for_carousel_generation() -> None:
    recommendations = [
        {"name": "Static card", "score": 9.6, "metadata": {"format_family": "static", "adaptation_score": 9.6}},
        {"name": "Carousel family A", "score": 8.9, "metadata": {"format_family": "carousel", "adaptation_score": 18.9}},
        {"name": "Carousel family B", "score": 8.7, "metadata": {"format_family": "carousel", "adaptation_score": 17.2}},
    ]

    filtered = ContentService._filter_template_recommendations_for_prompt(
        recommendations,
        prompt="Create a 5-slide carousel on retirement planning mistakes",
        follow_up_mode="new_content",
        studio_panel={"format": "carousel"},
    )

    assert [item["name"] for item in filtered] == ["Carousel family A", "Carousel family B"]


def test_sort_template_recommendations_for_format_places_best_adapting_candidate_first() -> None:
    recommendations = [
        {"name": "Carousel topic match", "score": 8.0, "metadata": {"format_family": "carousel", "adaptation_score": 21.0}},
        {"name": "Static stronger raw score", "score": 9.7, "metadata": {"format_family": "static", "adaptation_score": 9.7}},
        {"name": "Carousel weaker adaptation", "score": 8.4, "metadata": {"format_family": "carousel", "adaptation_score": 18.0}},
    ]

    ranked = ContentService._sort_template_recommendations_for_format(
        recommendations,
        studio_panel={"format": "carousel"},
    )

    assert [item["name"] for item in ranked] == [
        "Carousel topic match",
        "Carousel weaker adaptation",
        "Static stronger raw score",
    ]


def test_sort_template_recommendations_for_format_keeps_exact_family_ahead_of_mismatched_uploaded_sample() -> None:
    recommendations = [
        {
            "name": "Uploaded static sample",
            "score": 100.0,
            "match_type": "adapted_template",
            "metadata": {"format_family": "static", "adaptation_score": 200.0},
            "source": "request_reference_asset",
        },
        {
            "name": "Carousel family anchor",
            "score": 8.8,
            "match_type": "adapted_template",
            "metadata": {"format_family": "carousel", "adaptation_score": 22.8},
        },
    ]

    ranked = ContentService._sort_template_recommendations_for_format(
        recommendations,
        studio_panel={"format": "carousel"},
    )

    assert [item["name"] for item in ranked] == [
        "Carousel family anchor",
        "Uploaded static sample",
    ]


def test_collapse_carousel_template_recommendations_groups_same_family() -> None:
    recommendations = [
        {
            "template_id": str(uuid4()),
            "name": "Retirement-Planning-2",
            "display_name": "Retirement Planning",
            "score": 8.9,
            "format_family": "carousel",
            "recommendation_group_key": "RETIREMENT-PLANNING",
            "metadata": {
                "format_family": "carousel",
                "adaptation_score": 21.0,
                "sequence_family": "RETIREMENT-PLANNING",
                "sequence_position": 2,
                "family_display_name": "Retirement Planning",
            },
        },
        {
            "template_id": str(uuid4()),
            "name": "Retirement-Planning-1",
            "display_name": "Retirement Planning",
            "score": 9.1,
            "format_family": "carousel",
            "recommendation_group_key": "RETIREMENT-PLANNING",
            "metadata": {
                "format_family": "carousel",
                "adaptation_score": 22.0,
                "sequence_family": "RETIREMENT-PLANNING",
                "sequence_position": 1,
                "family_display_name": "Retirement Planning",
            },
        },
        {
            "template_id": str(uuid4()),
            "name": "Bond-Mistakes-1",
            "display_name": "Bond Mistakes",
            "score": 8.0,
            "format_family": "carousel",
            "recommendation_group_key": "BOND-MISTAKES",
            "metadata": {
                "format_family": "carousel",
                "adaptation_score": 18.0,
                "sequence_family": "BOND-MISTAKES",
                "sequence_position": 1,
                "family_display_name": "Bond Mistakes",
            },
        },
    ]

    collapsed = ContentService._collapse_carousel_template_recommendations(
        recommendations,
        studio_panel={"format": "carousel"},
    )

    assert [item["display_name"] for item in collapsed] == ["Retirement Planning", "Bond Mistakes"]
    assert collapsed[0]["metadata"]["family_member_count"] == 2
    assert collapsed[0]["metadata"]["group_type"] == "carousel_family"


def test_annotate_template_recommendation_selection_marks_primary_and_reason() -> None:
    recommendations = [
        {
            "template_id": str(uuid4()),
            "name": "Retirement-Planning-1",
            "display_name": "Retirement Planning",
            "format_family": "carousel",
            "metadata": {"format_family": "carousel"},
        },
        {
            "template_id": str(uuid4()),
            "name": "Bond-Mistakes-1",
            "display_name": "Bond Mistakes",
            "format_family": "carousel",
            "metadata": {"format_family": "carousel"},
        },
    ]

    annotated = ContentService._annotate_template_recommendation_selection(
        recommendations,
        studio_panel={"format": "carousel"},
    )

    assert annotated[0]["is_primary_adaptation"] is True
    assert annotated[0]["selection_reason"] == "Best Adaptation"
    assert annotated[1]["is_primary_adaptation"] is False
    assert annotated[1]["selection_reason"] == "Carousel Match"


@pytest.mark.asyncio
async def test_resolve_generation_decision_records_primary_adaptation_alignment() -> None:
    service = ContentService.__new__(ContentService)
    service.layout_decision = SimpleNamespace(
        decide=lambda **kwargs: LayoutDecision(
            mode="adapted_template",
            template_id="11111111-1111-1111-1111-111111111111",
            template_name="Retirement Planning",
            rationale=["Use the strongest carousel family anchor."],
            score_breakdown={},
            adaptation_plan={},
            brand_rule_hints={},
            asset_strategy={},
            review_flags=[],
        )
    )

    decision = await service._resolve_generation_decision(
        prompt="Create a 5-slide carousel on retirement planning mistakes",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        brand_context={},
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "11111111-1111-1111-1111-111111111111",
                "name": "Retirement Planning",
                "display_name": "Retirement Planning",
                "format_family": "carousel",
                "is_primary_adaptation": True,
                "selection_reason": "Best Adaptation",
            },
            {
                "template_id": "22222222-2222-2222-2222-222222222222",
                "name": "Bond Mistakes",
                "display_name": "Bond Mistakes",
                "format_family": "carousel",
                "is_primary_adaptation": False,
                "selection_reason": "Carousel Match",
            },
        ],
        selected_template_id=None,
        selected_template_name=None,
        reference_assets=[],
    )

    assert decision["primary_adaptation_template_id"] == "11111111-1111-1111-1111-111111111111"
    assert decision["primary_adaptation_template_name"] == "Retirement Planning"
    assert decision["primary_adaptation_selection_reason"] == "Best Adaptation"
    assert decision["primary_adaptation_matches_selected_template"] is True


def test_resolve_generation_selection_ids_ignores_inherited_ids_for_new_content() -> None:
    payload = SimpleNamespace(
        persona_id=None,
        objective_id=None,
        template_id=None,
    )

    follow_up_mode, persona_id, objective_id, template_id = ContentService._resolve_generation_selection_ids(
        payload=payload,
        session_memory={
            "follow_up_intent": {"mode": "new_content", "uses_previous_output": False},
            "inherited_persona_id": "11111111-1111-1111-1111-111111111111",
            "inherited_objective_id": "22222222-2222-2222-2222-222222222222",
            "inherited_template_id": "33333333-3333-3333-3333-333333333333",
        },
    )

    assert follow_up_mode == "new_content"
    assert persona_id is None
    assert objective_id is None
    assert template_id is None


def test_resolve_generation_selection_ids_preserves_inherited_ids_for_true_follow_ups() -> None:
    payload = SimpleNamespace(
        persona_id=None,
        objective_id=None,
        template_id=None,
    )

    follow_up_mode, persona_id, objective_id, template_id = ContentService._resolve_generation_selection_ids(
        payload=payload,
        session_memory={
            "follow_up_intent": {"mode": "modify_previous", "uses_previous_output": True},
            "inherited_persona_id": "11111111-1111-1111-1111-111111111111",
            "inherited_objective_id": "22222222-2222-2222-2222-222222222222",
            "inherited_template_id": "33333333-3333-3333-3333-333333333333",
        },
    )

    assert follow_up_mode == "modify_previous"
    assert str(persona_id) == "11111111-1111-1111-1111-111111111111"
    assert str(objective_id) == "22222222-2222-2222-2222-222222222222"
    assert str(template_id) == "33333333-3333-3333-3333-333333333333"


def test_resolve_generation_selection_ids_prefers_explicit_request_mode_over_session_memory() -> None:
    payload = SimpleNamespace(
        persona_id=None,
        objective_id=None,
        template_id=None,
        request_mode="new_content",
        inheritance_policy=SimpleNamespace(
            inherit_persona=False,
            inherit_objective=False,
            inherit_template=False,
        ),
    )

    follow_up_mode, persona_id, objective_id, template_id = ContentService._resolve_generation_selection_ids(
        payload=payload,
        session_memory={
            "follow_up_intent": {"mode": "variant_of_previous", "uses_previous_output": True},
            "inherited_persona_id": "11111111-1111-1111-1111-111111111111",
            "inherited_objective_id": "22222222-2222-2222-2222-222222222222",
            "inherited_template_id": "33333333-3333-3333-3333-333333333333",
        },
    )

    assert follow_up_mode == "new_content"
    assert persona_id is None
    assert objective_id is None
    assert template_id is None


def test_build_prompt_diagnostics_flags_regeneration_wrapper_and_message_mismatch() -> None:
    prompt = (
        "create a post for Women Borrowers are reshaping the credit market in India.\n\n"
        "Revise the existing creative with this instruction: Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement."
    )
    diagnostics = ContentService._build_prompt_diagnostics(
        prompt=prompt,
        session_memory={
            "follow_up_intent": {"mode": "variant_of_previous", "uses_previous_output": True},
            "latest_content_version": {"prompt": "create a post for Women Borrowers are reshaping the credit market in India."},
            "recent_messages": [
                {"role": "assistant", "message_text": "I couldn't generate the visual this time. Please regenerate."},
                {"role": "user", "message_text": "Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement."},
            ],
        },
    )

    assert diagnostics["contains_regeneration_wrapper"] is True
    assert diagnostics["wrapper_count"] == 1
    assert diagnostics["starts_with_latest_content_prompt"] is True
    assert diagnostics["matches_latest_user_message"] is False
    assert diagnostics["latest_user_message_excerpt"] == "Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement."


def test_source_prompt_for_rewrite_prefers_prompt_lineage_raw_prompt() -> None:
    content = SimpleNamespace(
        prompt="Revise the existing creative with this instruction: Make it sharper.",
        explainability_metadata={
            "prompt_lineage": {
                "user_prompt_raw": "Create a LinkedIn carousel about Census 2027 and investing.",
                "generation_prompt_effective": "Revise wrapper prompt",
            }
        },
    )

    assert (
        ContentService._source_prompt_for_rewrite(content)
        == "Create a LinkedIn carousel about Census 2027 and investing."
    )


def test_sanitize_prompt_for_request_prefers_raw_user_prompt_for_new_content_when_wrapper_detected() -> None:
    payload = SimpleNamespace(
        prompt=(
            "create a post for Women Borrowers are reshaping the credit market in India.\n\n"
            "Revise the existing creative with this instruction: Create a LinkedIn carousel about Census 2027."
        ),
        raw_user_prompt="Create a LinkedIn carousel about Census 2027.",
        request_mode="new_content",
    )

    sanitized_prompt, details = ContentService._sanitize_prompt_for_request(
        payload=payload,
        session_memory={
            "follow_up_intent": {"mode": "variant_of_previous", "uses_previous_output": True},
            "latest_content_version": {"prompt": "create a post for Women Borrowers are reshaping the credit market in India."},
            "recent_messages": [
                {"role": "user", "message_text": "Create a LinkedIn carousel about Census 2027."},
            ],
        },
    )

    assert sanitized_prompt == "Create a LinkedIn carousel about Census 2027."
    assert "contains_regeneration_wrapper" in details["contamination_signals"]
    assert "starts_with_latest_content_prompt" in details["contamination_signals"]


@pytest.mark.asyncio
async def test_resolve_logo_asset_path_falls_back_when_identity_path_is_stale() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    fallback_asset_id = uuid4()
    knowledge_asset = KnowledgeAsset(
        id=fallback_asset_id,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        name="Jiraaf logo",
        original_filename="logo.png",
        mime_type="image/png",
        storage_path="tenant/brand/logo/logo.png",
        lifecycle_state="indexed",
        channel="brand",
        field_key="logo",
        metadata_json={},
        validation_state="clean",
    )

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path == "tenant/brand/logo/logo.png"

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return knowledge_asset if asset_id == fallback_asset_id else None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return [knowledge_asset] if field_key == "logo" else []

    service.storage = _Storage()
    service.assets = _AssetRepo()
    service.knowledge_assets = _KnowledgeRepo()

    resolved = await service._resolve_logo_asset_path(
        tenant_id,
        brand_space_id,
        {
            "identity": {
                "logo_asset_path": "tenant/brand/logo/stale-logo.png",
                "logo_asset_id": str(fallback_asset_id),
            }
        },
    )

    assert resolved == "tenant/brand/logo/logo.png"


@pytest.mark.asyncio
async def test_resolve_logo_asset_path_discovers_logo_file_from_storage_when_metadata_is_missing() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    root = Path("tests") / f"logo-discovery-{uuid4()}"
    logo_file = root / str(tenant_id) / str(brand_space_id) / "logo" / "jiraaf-primary-logo.png"
    logo_file.parent.mkdir(parents=True, exist_ok=True)
    logo_file.write_bytes(b"png")

    class _Storage:
        def __init__(self, base_path):
            self.base_path = base_path

        def exists(self, storage_path: str) -> bool:
            return (self.base_path / storage_path).exists()

        def absolute_path(self, storage_path: str) -> str:
            return str((self.base_path / storage_path).resolve())

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    try:
        service.storage = _Storage(root)
        service.assets = _AssetRepo()
        service.knowledge_assets = _KnowledgeRepo()

        resolved = await service._resolve_logo_asset_path(
            tenant_id,
            brand_space_id,
            {
                "identity": {
                    "logo_asset_path": f"{tenant_id}/{brand_space_id}/logo/stale-logo.png",
                }
            },
        )

        assert resolved == f"{tenant_id}/{brand_space_id}/logo/jiraaf-primary-logo.png"
    finally:
        for file in root.rglob("*"):
            if file.is_file():
                file.unlink()
        for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
            directory.rmdir()
        root.rmdir()


@pytest.mark.asyncio
async def test_resolve_logo_asset_path_ignores_non_logo_derived_assets_during_storage_discovery() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    root = Path("tests") / f"logo-discovery-derived-{uuid4()}"
    logo_file = root / str(tenant_id) / str(brand_space_id) / "logo" / "jiraaf-primary-logo.png"
    derived_icon = root / str(tenant_id) / str(brand_space_id) / "derived-assets" / "Representation-of-Icons-in-primary-color.png"
    logo_file.parent.mkdir(parents=True, exist_ok=True)
    derived_icon.parent.mkdir(parents=True, exist_ok=True)
    logo_file.write_bytes(b"png")
    derived_icon.write_bytes(b"png")

    class _Storage:
        def __init__(self, base_path):
            self.base_path = base_path

        def exists(self, storage_path: str) -> bool:
            return (self.base_path / storage_path).exists()

        def absolute_path(self, storage_path: str) -> str:
            return str((self.base_path / storage_path).resolve())

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    class _ReusableAssetRepo:
        async def list_by_brand(self, brand_space_id, tenant_id=None, active_only=True):
            return []

    try:
        service.storage = _Storage(root)
        service.assets = _AssetRepo()
        service.knowledge_assets = _KnowledgeRepo()
        service.reusable_assets = _ReusableAssetRepo()

        resolved = await service._resolve_logo_asset_path(
            tenant_id,
            brand_space_id,
            {"identity": {}, "visual_identity": {}},
        )

        assert resolved == f"{tenant_id}/{brand_space_id}/logo/jiraaf-primary-logo.png"
    finally:
        for file in root.rglob("*"):
            if file.is_file():
                file.unlink()
        for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
            directory.rmdir()
        root.rmdir()


@pytest.mark.asyncio
async def test_resolve_logo_asset_path_prefers_dark_logo_variant_for_light_background() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path in {
                "tenant/brand/logo/logo-light.png",
                "tenant/brand/logo/logo-dark.png",
            }

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    service.storage = _Storage()
    service.assets = _AssetRepo()
    service.knowledge_assets = _KnowledgeRepo()

    resolved = await service._resolve_logo_asset_path(
        tenant_id,
        brand_space_id,
        {
            "identity": {
                "logo_assets": [
                    {
                        "storage_path": "tenant/brand/logo/logo-light.png",
                        "variant": "light",
                        "trust_level": "trusted",
                    },
                    {
                        "storage_path": "tenant/brand/logo/logo-dark.png",
                        "variant": "dark",
                        "trust_level": "trusted",
                    },
                ]
            },
            "visual_identity": {
                "brand_color_palette": {
                    "background": "#F5F1E9",
                    "primary": "#003975",
                }
            },
        },
        studio_panel={"format": "static", "platform_preset": "instagram", "size": {"width": 1080, "height": 1080}},
    )

    assert resolved == "tenant/brand/logo/logo-dark.png"


@pytest.mark.asyncio
async def test_resolve_logo_asset_path_prefers_horizontal_lockup_for_wide_canvas() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path in {
                "tenant/brand/logo/logo-stacked.png",
                "tenant/brand/logo/logo-horizontal.png",
            }

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    service.storage = _Storage()
    service.assets = _AssetRepo()
    service.knowledge_assets = _KnowledgeRepo()

    resolved = await service._resolve_logo_asset_path(
        tenant_id,
        brand_space_id,
        {
            "identity": {
                "logo_assets": [
                    {
                        "storage_path": "tenant/brand/logo/logo-stacked.png",
                        "orientation": "stacked",
                        "trust_level": "trusted",
                    },
                    {
                        "storage_path": "tenant/brand/logo/logo-horizontal.png",
                        "orientation": "horizontal",
                        "trust_level": "trusted",
                    },
                ]
            },
            "visual_identity": {
                "brand_color_palette": {
                    "background": "#FFFFFF",
                    "primary": "#003975",
                }
            },
        },
        studio_panel={"format": "poster", "platform_preset": "youtube", "size": {"width": 1280, "height": 720}},
    )

    assert resolved == "tenant/brand/logo/logo-horizontal.png"


@pytest.mark.asyncio
async def test_resolve_logo_asset_selection_allows_requested_variant_to_override_heuristic_default() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path in {
                "tenant/brand/logo/logo-light.png",
                "tenant/brand/logo/logo-dark.png",
            }

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    service.storage = _Storage()
    service.assets = _AssetRepo()
    service.knowledge_assets = _KnowledgeRepo()

    candidates = await service._collect_logo_asset_candidates(
        tenant_id,
        brand_space_id,
        {
            "identity": {
                "logo_assets": [
                    {
                        "storage_path": "tenant/brand/logo/logo-light.png",
                        "variant": "light",
                        "trust_level": "trusted",
                    },
                    {
                        "storage_path": "tenant/brand/logo/logo-dark.png",
                        "variant": "dark",
                        "trust_level": "trusted",
                    },
                ]
            }
        },
    )

    selection = await service._resolve_logo_asset_selection(
        tenant_id,
        brand_space_id,
        {
            "visual_identity": {
                "brand_color_palette": {
                    "background": "#F5F1E9",
                    "primary": "#003975",
                }
            }
        },
        studio_panel={"format": "static", "platform_preset": "instagram", "size": {"width": 1080, "height": 1080}},
        requested_variant="light_on_dark",
        candidates=candidates,
    )

    assert selection is not None
    assert selection["storage_path"] == "tenant/brand/logo/logo-light.png"


@pytest.mark.asyncio
async def test_resolve_logo_asset_path_falls_back_to_identity_section_payload() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path == "tenant/brand/uploads/logo-from-section.png"

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    class _SectionRepo:
        async def list_current_sections(self, brand_space_id, tenant_id=None):
            return [
                SimpleNamespace(
                    section_code="identity",
                    payload={
                        "logo_asset_path": "tenant/brand/uploads/logo-from-section.png",
                        "logo_assets": [
                            {
                                "storage_path": "tenant/brand/uploads/logo-from-section.png",
                                "trust_level": "trusted",
                                "background_variant": "light",
                            }
                        ],
                    },
                )
            ]

    service.storage = _Storage()
    service.assets = _AssetRepo()
    service.knowledge_assets = _KnowledgeRepo()
    service.sections = _SectionRepo()

    resolved = await service._resolve_logo_asset_path(
        tenant_id,
        brand_space_id,
        {
            "identity": {},
            "visual_identity": {
                "brand_color_palette": {
                    "background": "#F8F5EF",
                    "primary": "#003975",
                }
            },
        },
        studio_panel={"format": "static", "platform_preset": "instagram", "size": {"width": 1080, "height": 1080}},
    )

    assert resolved == "tenant/brand/uploads/logo-from-section.png"


@pytest.mark.asyncio
async def test_resolve_logo_asset_path_falls_back_to_reusable_logo_variant() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path == "tenant/brand/derived-assets/logo-variant-wordmark.png"

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    class _ReusableAssetRepo:
        async def list_by_brand(self, brand_space_id, tenant_id=None, active_only=True):
            return [
                SimpleNamespace(
                    storage_path="tenant/brand/derived-assets/logo-variant-wordmark.png",
                    label="logo variant: Jiraaf wordmark",
                    asset_kind="logo_variant",
                    normalized_metadata_json={"review_class": "logo", "review_status": "approved"},
                    source_metadata_json={"source_filename": "jiraaf-wordmark.pdf"},
                )
            ]

    service.storage = _Storage()
    service.assets = _AssetRepo()
    service.knowledge_assets = _KnowledgeRepo()
    service.reusable_assets = _ReusableAssetRepo()

    resolved = await service._resolve_logo_asset_path(
        tenant_id,
        brand_space_id,
        {"identity": {}, "visual_identity": {}},
    )

    assert resolved == "tenant/brand/derived-assets/logo-variant-wordmark.png"


@pytest.mark.asyncio
async def test_prepare_runtime_brand_context_enriches_logo_palette_and_reusable_assets() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    logo_path = "tenant/brand/uploads/jiraaf-logo.png"

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path in {logo_path, "tenant/brand/derived-assets/coin-icon.png"}

    class _AssetRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

    class _KnowledgeRepo:
        async def get_scoped(self, asset_id, tenant_id, brand_space_id):
            return None

        async def list_by_field(self, brand_space_id, field_key, tenant_id=None, active_only=False):
            return []

    class _ReusableAssetRepo:
        async def list_by_brand(self, brand_space_id, tenant_id=None, active_only=True):
            return [
                SimpleNamespace(
                    id=uuid4(),
                    asset_kind="icon",
                    review_class="decorative",
                    review_status="approved",
                    review_reason="Approved icon",
                    mime_type="image/png",
                    storage_path="tenant/brand/derived-assets/coin-icon.png",
                    label="Coin icon",
                    source_asset_id=None,
                    source_metadata_json={"origin_category": "visual_identity"},
                    normalized_metadata_json={"render_eligible": True},
                    trust_level="trusted",
                    width=128,
                    height=128,
                )
            ]

    service.storage = _Storage()
    service.assets = _AssetRepo()
    service.knowledge_assets = _KnowledgeRepo()
    service.reusable_assets = _ReusableAssetRepo()

    runtime_brand_context, logo_candidates, logo_selection = await service._prepare_runtime_brand_context(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        brand_context={"brand_name": "Jiraaf", "identity": {}, "visual_identity": {}},
        studio_panel={"format": "static", "platform_preset": "instagram", "size": {"width": 1080, "height": 1080}},
        sections=[
            SimpleNamespace(
                section_code="identity",
                payload={
                    "logo_asset_path": logo_path,
                    "logo_assets": [
                        {
                            "storage_path": logo_path,
                            "trust_level": "trusted",
                            "background_variant": "light",
                            "logo_colors": [
                                {"hex_code": "#D8A028", "role": "primary"},
                                {"hex_code": "#123A7A", "role": "secondary"},
                            ],
                        }
                    ],
                },
            ),
            SimpleNamespace(
                section_code="visual_identity",
                payload={
                    "typography": {"font_families": [{"name": "DM Sans"}]},
                },
            ),
        ],
    )

    assert logo_candidates
    assert logo_selection is not None
    assert runtime_brand_context["identity"]["logo_asset_path"] == logo_path
    assert runtime_brand_context["visual_identity"]["brand_color_palette"]["primary"] == "#D8A028"
    assert runtime_brand_context["visual_identity"]["brand_color_palette"]["secondary"] == "#123A7A"
    assert runtime_brand_context["visual_identity"]["typography"]["font_families"][0]["name"] == "DM Sans"
    assert runtime_brand_context["visual_identity"]["reusable_design_assets"][0]["asset_kind"] == "icon"


def test_reusable_asset_payload_serializes_extracted_design_asset() -> None:
    payload = ContentService._reusable_asset_payload(
        {
            "id": str(uuid4()),
            "asset_kind": "decorative_asset",
            "review_class": "decorative",
            "review_status": "approved",
            "review_reason": "Mood-board decorative asset approved for renderer accents.",
            "mime_type": "image/png",
            "storage_path": "tenant/brand/derived-assets/pattern.png",
            "label": "Pattern Bloom",
            "source_asset_id": str(uuid4()),
            "source_metadata": {"origin_category": "mood_board"},
            "normalized_metadata": {"render_eligible": True},
            "trust_level": "usable_with_warning",
        }
    )

    assert payload["asset_role"] == "decorative_asset"
    assert payload["storage_path"].endswith("pattern.png")
    assert payload["trust_level"] == "usable_with_warning"
    assert payload["validation_state"] == "warning"
    assert payload["metadata"]["review_class"] == "decorative"
    assert payload["metadata"]["review_status"] == "approved"


def test_resolve_render_font_assets_uses_uploaded_brand_fonts() -> None:
    font_paths = ContentService._resolve_render_font_assets(
        {
            "visual_identity": {
                "typography": {
                    "uploaded_font_assets": [
                        {
                            "storage_path": "tenant/brand/uploads/fonts/BrandDisplay-Regular.ttf",
                            "trust_level": "trusted",
                        },
                        {
                            "storage_path": "tenant/brand/uploads/fonts/BrandBody-Regular.ttf",
                            "trust_level": "usable_with_warning",
                        },
                        {
                            "storage_path": "tenant/brand/uploads/fonts/IgnoreMe.ttf",
                            "trust_level": "excluded",
                        },
                    ]
                }
            }
        }
    )

    assert font_paths == [
        "tenant/brand/uploads/fonts/BrandDisplay-Regular.ttf",
        "tenant/brand/uploads/fonts/BrandBody-Regular.ttf",
    ]


def test_build_ai_final_render_export_payload_composites_logo_when_ai_skips_it() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    root = Path("tests") / f"ai-final-render-logo-{uuid4()}"

    class _Storage:
        def __init__(self, base_path: Path) -> None:
            self.base_path = base_path

        def exists(self, storage_path: str) -> bool:
            return (self.base_path / storage_path).exists()

        def absolute_path(self, storage_path: str) -> str:
            return str((self.base_path / storage_path).resolve())

        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            relative = f"{category}/{filename}"
            target = self.base_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return SimpleNamespace(storage_path=relative, absolute_path=str(target.resolve()))

    service.storage = _Storage(root)

    final_render_path = f"{tenant_id}/{brand_space_id}/generated/final-render.png"
    logo_path = f"{tenant_id}/{brand_space_id}/uploads/jiraaf-logo.png"
    final_render_file = root / final_render_path
    final_render_file.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (1080, 1080), (255, 255, 255, 255)).save(final_render_file, format="PNG")

    logo_file = root / logo_path
    logo_file.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (320, 160), (10, 40, 160, 255)).save(logo_file, format="PNG")

    content = ContentVersion(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a social post",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={},
        blueprint_payload={
            "zones": [
                {"zone_id": "logo", "role": "logo", "x": 860, "y": 48, "width": 160, "height": 80},
            ]
        },
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_preview",
        mime_type="image/png",
        storage_path=final_render_path,
        width=1080,
        height=1080,
        metadata_json={"render_source": "ai", "generation_stage": "final_render"},
    )

    payload = service._build_ai_final_render_export_payload(
        content=content,
        asset=asset,
        explainability={"scene_graph": {"elements": []}, "generation_path": "ai_final_render"},
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        selected_template_id=None,
        logo_asset_path=logo_path,
    )

    preview_asset = payload["preview_asset"]
    export_asset = payload["export_assets"][0]
    composited_output = root / preview_asset["storage_path"]

    assert payload["renderer_metadata"]["logo_rendered"] is True
    assert payload["renderer_metadata"]["render_manifest"]["logo_fallback_composited"] is True
    assert preview_asset["storage_path"] != final_render_path
    assert export_asset["storage_path"] == preview_asset["storage_path"]
    assert composited_output.exists()

    with Image.open(composited_output) as rendered:
        assert rendered.getpixel((940, 80))[:3] == (10, 40, 160)

    if root.exists():
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        root.rmdir()


def test_build_ai_logo_fallback_asset_clears_reserved_logo_zone_for_transparent_logo() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    final_render_path = f"{tenant_id}/{brand_space_id}/generated/final-render.png"
    logo_path = f"{tenant_id}/{brand_space_id}/logo/jiraaf.png"
    base = Image.new("RGBA", (1080, 1080), (248, 246, 238, 255))
    for x in range(700, 1020):
        shade = 232 + ((x - 700) % 40)
        for y in range(0, 180):
            base.putpixel((x, y), (shade, 244, 250, 255))
    logo = Image.new("RGBA", (220, 90), (0, 0, 0, 0))
    for x in range(70, 150):
        for y in range(25, 65):
            logo.putpixel((x, y), (245, 158, 11, 255))

    content = ContentVersion(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a social post",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={"metadata": {"logo_position": "Top-right corner for clear brand presence with enough margin"}},
        blueprint_payload={},
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_preview",
        mime_type="image/png",
        storage_path=final_render_path,
        width=1080,
        height=1080,
        metadata_json={"render_source": "ai", "generation_stage": "final_render"},
    )

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path in {final_render_path, logo_path}

        def absolute_path(self, storage_path: str) -> str:
            return storage_path

    @contextmanager
    def _open_image_asset(path: str):
        if path == final_render_path:
            yield base.copy()
            return
        if path == logo_path:
            yield logo.copy()
            return
        raise OSError(path)

    service.storage = _Storage()
    service._resolve_ai_logo_box = lambda **kwargs: (780, 42, 220, 90)  # type: ignore[method-assign]
    service._select_logo_overlay_candidate = lambda **kwargs: None  # type: ignore[method-assign]
    service._strip_logo_background_if_safe = lambda image: image  # type: ignore[method-assign]
    service._trim_transparent_logo_margins = lambda image: image  # type: ignore[method-assign]
    service._logo_box_background_luminance = lambda *args, **kwargs: 220  # type: ignore[method-assign]
    captured: dict[str, Image.Image] = {}

    def _store_image(**kwargs):  # type: ignore[no-untyped-def]
        captured["image"] = kwargs["image"].copy()
        return {
            "asset_id": str(uuid4()),
            "mime_type": "image/png",
            "storage_path": "generated/exact-logo.png",
            "width": 1080,
            "height": 1080,
        }

    service._store_ai_final_render_image = _store_image  # type: ignore[method-assign]

    import app.services.content as content_module

    original_open_image_asset = content_module.open_image_asset
    content_module.open_image_asset = _open_image_asset

    try:
        payload = service._build_ai_logo_fallback_asset(
            content=content,
            asset=asset,
            explainability={"scene_graph": {"elements": []}, "generation_path": "ai_final_render"},
            studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
            logo_asset_path=logo_path,
        )
    finally:
        content_module.open_image_asset = original_open_image_asset

    assert payload is not None
    assert payload["metadata"]["logo_clearance_zone_applied"] is True
    assert "image" in captured
    left_sample = captured["image"].getpixel((790, 52))[:3]
    right_sample = captured["image"].getpixel((970, 52))[:3]
    assert left_sample != right_sample


def test_build_ai_footer_fallback_asset_stamps_exact_legal_footer() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    final_render_path = f"{tenant_id}/{brand_space_id}/generated/final-render.png"
    base = Image.new("RGBA", (1024, 1536), (248, 253, 255, 255))
    footer_text = (
        "Jiraaf Platform Private Limited ; SEBI Registration Number ( Stock Broker ) : INZ000315538 "
        "Disclaimer : Fixed returns do not constitute guaranteed or assured returns ."
    )
    content = ContentVersion(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a carousel",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        generated_payload={},
        blueprint_payload={},
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_preview",
        mime_type="image/png",
        storage_path=final_render_path,
        width=1024,
        height=1536,
        metadata_json={"render_source": "ai", "generation_stage": "final_render"},
    )

    class _Storage:
        def exists(self, storage_path: str) -> bool:
            return storage_path == final_render_path

        def absolute_path(self, storage_path: str) -> str:
            return storage_path

    @contextmanager
    def _open_image_asset(path: str):
        if path == final_render_path:
            yield base.copy()
            return
        raise OSError(path)

    captured: dict[str, Image.Image] = {}

    def _store_image(**kwargs):  # type: ignore[no-untyped-def]
        captured["image"] = kwargs["image"].copy()
        return {
            "asset_id": str(uuid4()),
            "mime_type": "image/png",
            "storage_path": "generated/exact-footer.png",
            "width": 1024,
            "height": 1536,
        }

    service.storage = _Storage()
    service._store_ai_final_render_image = _store_image  # type: ignore[method-assign]

    import app.services.content as content_module

    original_open_image_asset = content_module.open_image_asset
    content_module.open_image_asset = _open_image_asset

    try:
        payload = service._build_ai_footer_fallback_asset(
            content=content,
            asset=asset,
            explainability={
                "scene_graph": {
                    "elements": [
                        {
                            "element_id": "legal_footer",
                            "role": "legal",
                            "text": footer_text,
                        }
                    ]
                }
            },
            studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        )
    finally:
        content_module.open_image_asset = original_open_image_asset

    assert payload is not None
    assert payload["metadata"]["legal_footer_composited_by_service"] is True
    assert payload["metadata"]["legal_footer_text_length"] == len(footer_text)
    assert "image" in captured
    assert captured["image"].getpixel((40, 1510))[:3] != base.getpixel((40, 1510))[:3]


def test_strip_logo_background_if_safe_removes_dark_matte_edges() -> None:
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 255))
    for x in range(24, 96):
        for y in range(20, 60):
            image.putpixel((x, y), (0, 57, 117, 255))
    for x in range(8, 22):
        for y in range(18, 62):
            image.putpixel((x, y), (245, 164, 24, 255))

    cleaned = ContentService._strip_logo_background_if_safe(image)
    assert cleaned.getpixel((0, 0))[3] == 0
    assert cleaned.getpixel((30, 30))[3] == 255


def test_build_ai_final_render_export_payloads_convert_pdf_without_renderer_fallback() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    root = Path("tests") / f"ai-final-render-pdf-{uuid4()}"

    class _Storage:
        def __init__(self, base_path: Path) -> None:
            self.base_path = base_path

        def exists(self, storage_path: str) -> bool:
            return (self.base_path / storage_path).exists()

        def absolute_path(self, storage_path: str) -> str:
            return str((self.base_path / storage_path).resolve())

        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            relative = f"{category}/{filename}"
            target = self.base_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return SimpleNamespace(storage_path=relative, absolute_path=str(target.resolve()))

    service.storage = _Storage(root)

    slide_one = f"{tenant_id}/{brand_space_id}/generated/slide-one.png"
    slide_two = f"{tenant_id}/{brand_space_id}/generated/slide-two.png"
    for storage_path, color in ((slide_one, (12, 34, 56, 255)), (slide_two, (78, 90, 120, 255))):
        target = root / storage_path
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (1080, 1080), color).save(target, format="PNG")

    content = ContentVersion(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a carousel",
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "pdf"},
        generated_payload={},
        blueprint_payload={},
        explainability_metadata={},
    )
    assets = [
        GeneratedAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=uuid4(),
            asset_role="render_preview",
            mime_type="image/png",
            storage_path=slide_one,
            width=1080,
            height=1080,
            metadata_json={"render_source": "ai", "slide_index": 1, "slide_count": 2},
        ),
        GeneratedAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=uuid4(),
            asset_role="render_export",
            mime_type="image/png",
            storage_path=slide_two,
            width=1080,
            height=1080,
            metadata_json={"render_source": "ai", "slide_index": 2, "slide_count": 2},
        ),
    ]

    payload = service._build_ai_final_render_export_payloads(
        content=content,
        assets=assets,
        explainability={"scene_graph": {"elements": []}, "generation_path": "ai_final_render"},
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "pdf"},
        selected_template_id=None,
        logo_asset_path=None,
    )

    assert payload["preview_asset"]["mime_type"] == "image/png"
    assert payload["export_assets"][0]["mime_type"] == "application/pdf"
    assert payload["renderer_metadata"]["output_file_type"] == "pdf"
    assert (root / payload["export_assets"][0]["storage_path"]).exists()

    if root.exists():
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        root.rmdir()


def test_build_ai_final_render_export_payloads_returns_multi_slide_export_for_carousel() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    content = ContentVersion(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a carousel",
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={},
        blueprint_payload={},
        explainability_metadata={},
    )
    assets = [
        GeneratedAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=uuid4(),
            asset_role="render_preview" if index == 1 else "render_export",
            mime_type="image/png",
            storage_path=f"{tenant_id}/{brand_space_id}/generated/final-render-slide-{index}.png",
            width=1080,
            height=1080,
            metadata_json={"render_source": "ai", "generation_stage": "final_render", "slide_index": index, "slide_count": 3},
        )
        for index in range(1, 4)
    ]

    payload = service._build_ai_final_render_export_payloads(
        content=content,
        assets=assets,
        explainability={"scene_graph": {"elements": []}, "generation_path": "ai_final_render", "creative_decision": {}},
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        selected_template_id=None,
        logo_asset_path=None,
    )

    assert payload["preview_asset"]["storage_path"].endswith("final-render-slide-1.png")
    assert len(payload["export_assets"]) == 3
    assert payload["renderer_metadata"]["layout_variant"] == "ai_final_render_carousel"
    assert payload["renderer_metadata"]["page_count"] == 3
    assert payload["renderer_metadata"]["render_manifest"]["carousel_slide_count"] == 3


def test_resolve_ai_logo_box_prefers_top_right_hint_and_minimum_size() -> None:
    content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a carousel",
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={"metadata": {"logo_position": "Top-right corner for clear brand presence with enough margin"}},
        blueprint_payload={},
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=content.tenant_id,
        brand_space_id=content.brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_export",
        mime_type="image/png",
        storage_path="tenant/brand/generated/slide-1.png",
        width=1080,
        height=1080,
        metadata_json={},
    )

    box = ContentService._resolve_ai_logo_box(
        content=content,
        explainability={
            "scene_graph": {
                "elements": [
                    {
                        "role": "logo",
                        "geometry": {"x": 60, "y": 980, "width": 180, "height": 40, "units": "px"},
                    }
                ]
            }
        },
        studio_panel={"format": "carousel", "size": {"width": 1080, "height": 1080}},
        asset=asset,
    )

    assert box[0] >= 780
    assert box[1] <= 60
    assert box[2] >= 220
    assert box[3] >= 90


def test_resolve_ai_logo_box_uses_reference_creative_logo_ratio_for_top_right() -> None:
    content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a carousel",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        generated_payload={"metadata": {"logo_position": "top-right"}},
        blueprint_payload={},
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=content.tenant_id,
        brand_space_id=content.brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_export",
        mime_type="image/png",
        storage_path="tenant/brand/generated/slide-1.png",
        width=1080,
        height=1350,
        metadata_json={},
    )

    box = ContentService._resolve_ai_logo_box(
        content=content,
        explainability={
            "brand_context_snapshot": {
                "visual_identity": {
                    "reference_creatives": [
                        {"layout_structure": {"zones": [{"role": "logo", "x": 0.85, "y": 0.02, "w": 0.13, "h": 0.12}]}}
                    ]
                }
            },
            "scene_graph": {"elements": []},
        },
        studio_panel={"format": "carousel", "size": {"width": 1080, "height": 1350}},
        asset=asset,
    )

    assert box[2] >= 140
    assert box[3] >= 150
    assert box[0] >= 730
    assert box[1] <= 40


def test_expanded_logo_clearance_box_is_more_aggressive_for_carousel_top_right() -> None:
    image = Image.new("RGBA", (1080, 1350), (248, 246, 238, 255))
    box = (820, 24, 238, 135)

    generic = ContentService._expanded_logo_clearance_box(image, box, format_name="static")
    carousel = ContentService._expanded_logo_clearance_box(image, box, format_name="carousel")

    assert carousel[0] < generic[0]
    assert carousel[1] <= generic[1]
    assert carousel[2] > generic[2]
    assert carousel[3] > generic[3]


def test_logo_footprint_clearance_box_stays_tight_to_transparent_logo() -> None:
    image = Image.new("RGBA", (1080, 1350), (255, 255, 255, 255))

    clear_box = ContentService._logo_footprint_clearance_box(
        image=image,
        offset_x=782,
        offset_y=38,
        logo_width=156,
        logo_height=46,
    )

    assert clear_box[0] >= 760
    assert clear_box[1] >= 24
    assert clear_box[2] <= 190
    assert clear_box[3] <= 70


def test_clear_ai_logo_overlay_region_prefers_clean_top_band_for_top_right_logo() -> None:
    image = Image.new("RGBA", (1080, 1350), (252, 250, 245, 255))
    draw = ImageDraw.Draw(image)
    # Simulate the kind of ghosted text/noise that often bleeds in from the left.
    draw.rectangle((360, 40, 760, 150), fill=(82, 110, 145, 180))
    draw.rectangle((430, 0, 520, 165), fill=(120, 140, 168, 160))
    # Keep the very top band calm and bright.
    draw.rectangle((0, 0, 1080, 28), fill=(255, 254, 250, 255))
    # Give the surrounding page a warmer tone so a hard white plate would be obvious.
    draw.rectangle((0, 120, 1080, 320), fill=(244, 238, 229, 255))

    cleared, applied = ContentService._clear_ai_logo_overlay_region(
        image,
        (734, 54, 238, 135),
        format_name="carousel",
    )

    assert applied is True
    # The cleaned logo zone should inherit the calm top band rather than dark left-side noise.
    sample = cleared.getpixel((860, 90))
    assert sample[0] >= 235
    assert sample[1] >= 232
    assert sample[2] >= 228
    # The bottom edge should still blend toward the warmer page instead of looking like
    # a hard white tile underneath the logo.
    edge_sample = cleared.getpixel((860, 205))
    assert edge_sample[0] < 253
    assert edge_sample[1] < 252


def test_clear_ai_logo_footprint_region_avoids_rectangular_white_plate() -> None:
    image = Image.new("RGBA", (1080, 1350), (247, 240, 231, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((710, 40, 980, 170), fill=(120, 132, 150, 180))
    draw.rectangle((0, 0, 1080, 30), fill=(255, 252, 247, 255))

    logo = Image.new("RGBA", (180, 60), (0, 0, 0, 0))
    logo_draw = ImageDraw.Draw(logo)
    logo_draw.rounded_rectangle((8, 8, 48, 48), radius=10, fill=(255, 166, 0, 255))
    logo_draw.rectangle((62, 14, 170, 34), fill=(0, 57, 117, 255))
    logo_draw.rectangle((62, 38, 152, 50), fill=(0, 57, 117, 255))

    cleared, applied = ContentService._clear_ai_logo_footprint_region(
        image,
        logo_image=logo,
        offset_x=760,
        offset_y=38,
        clear_box=ContentService._logo_footprint_clearance_box(
            image=image,
            offset_x=760,
            offset_y=38,
            logo_width=180,
            logo_height=60,
        ),
    )

    assert applied is True
    # Under the logo footprint we should have removed the darker ghosted noise.
    cleaned_logo_sample = cleared.getpixel((820, 68))
    assert cleaned_logo_sample[0] >= 228
    assert cleaned_logo_sample[1] >= 222
    assert cleaned_logo_sample[2] >= 214
    # Just outside the logo footprint, the warmer page background should remain.
    outside_sample = cleared.getpixel((760, 122))
    assert outside_sample[0] <= 251
    assert outside_sample[1] <= 245
    assert outside_sample[2] <= 237


def test_resolve_ai_logo_box_uses_blueprint_logo_zone_id_when_role_is_missing() -> None:
    content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a static post",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={"metadata": {"logo_position": "Top-right corner for clear brand presence with enough margin"}},
        blueprint_payload={
            "zones": [
                {
                    "zone_id": "logo_top_right",
                    "x": 760,
                    "y": 48,
                    "width": 260,
                    "height": 100,
                    "units": "px",
                }
            ]
        },
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=content.tenant_id,
        brand_space_id=content.brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_export",
        mime_type="image/png",
        storage_path="tenant/brand/generated/static.png",
        width=1080,
        height=1080,
        metadata_json={},
    )

    box = ContentService._resolve_ai_logo_box(
        content=content,
        explainability={"scene_graph": {"elements": []}},
        studio_panel={"format": "static", "size": {"width": 1080, "height": 1080}},
        asset=asset,
    )

    assert box[0] == 760
    assert box[1] == 48
    assert box[2] == 260
    assert box[3] == 100


def test_resolve_ai_logo_box_uses_synthesized_blueprint_logo_zone_when_it_is_viable() -> None:
    content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a static post",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={},
        blueprint_payload={
            "source_mode": "synthesized_layout",
            "zones": [
                {
                    "zone_id": "logo_overlay",
                    "role": "logo",
                    "x": 80,
                    "y": 80,
                    "width": 160,
                    "height": 60,
                    "units": "px",
                }
            ],
        },
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=content.tenant_id,
        brand_space_id=content.brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_export",
        mime_type="image/png",
        storage_path="tenant/brand/generated/static.png",
        width=1080,
        height=1080,
        metadata_json={},
    )

    box = ContentService._resolve_ai_logo_box(
        content=content,
        explainability={"scene_graph": {"layout_mode": "synthesized_layout", "elements": []}},
        studio_panel={"format": "static", "size": {"width": 1080, "height": 1080}},
        asset=asset,
    )

    assert box == (80, 80, 160, 60)


def test_resolve_ai_logo_box_prefers_finalized_scene_graph_logo_over_stale_blueprint_zone() -> None:
    content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a static post",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={"metadata": {"logo_position": "bottom-right"}},
        blueprint_payload={
            "zones": [
                {
                    "zone_id": "logo_top_right",
                    "role": "logo",
                    "x": 760,
                    "y": 48,
                    "width": 260,
                    "height": 100,
                    "units": "px",
                }
            ]
        },
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=content.tenant_id,
        brand_space_id=content.brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_export",
        mime_type="image/png",
        storage_path="tenant/brand/generated/static.png",
        width=1080,
        height=1080,
        metadata_json={},
    )

    box = ContentService._resolve_ai_logo_box(
        content=content,
        explainability={
            "scene_graph": {
                "styles": {"logo_position": "bottom-right"},
                "validation_hints": {"logo_position": "bottom-right"},
                "elements": [
                    {
                        "role": "logo",
                        "geometry": {"x": 820, "y": 915, "width": 220, "height": 90, "units": "px"},
                    }
                ],
            }
        },
        studio_panel={"format": "static", "size": {"width": 1080, "height": 1080}},
        asset=asset,
    )

    assert box[0] >= 780
    assert box[1] >= 860
    assert box[2] >= 180
    assert box[3] >= 60


@pytest.mark.asyncio
async def test_build_ai_final_render_overlay_payloads_renders_exact_text_overlay_in_asset_order() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    content = ContentVersion(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a carousel",
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={"headline": "Default headline", "body": "Default body", "cta": "Explore", "hashtags": [], "metadata": {}},
        blueprint_payload={
            "layout_type": "carousel",
            "zones": [{"zone_id": "headline", "role": "headline", "x": 64, "y": 64, "width": 720, "height": 180}],
            "hierarchy": ["headline"],
            "text_blocks": [],
            "image_zones": [],
            "logo_rules": {},
            "cta_placement": {},
            "platform_preset": "instagram",
            "export_format": "png",
            "overflow_strategy": {"mode": "shrink_then_wrap"},
        },
        explainability_metadata={},
    )
    overlay_scene_graph = {
        "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
        "layout_mode": "synthesized_layout",
        "confidence": 0.8,
        "layers": ["content", "brand"],
        "elements": [
            {
                "element_id": "headline",
                "element_type": "text",
                "role": "headline",
                "geometry": {"x": 0.08, "y": 0.1, "width": 0.5, "height": 0.16, "units": "normalized"},
                "text": "Slide headline",
                "style": {"font_size": 64, "fill_role": "light_text"},
            },
            {
                "element_id": "supporting_line",
                "element_type": "text",
                "role": "supporting_line",
                "geometry": {"x": 0.08, "y": 0.28, "width": 0.62, "height": 0.16, "units": "normalized"},
                "text": "Original support",
                "style": {"font_size": 28, "fill_role": "light_text"},
            }
        ],
        "styles": {},
        "assets": [],
        "template_adaptation": {},
        "validation_hints": {},
    }
    assets = [
        GeneratedAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=uuid4(),
            asset_role="render_preview" if index == 1 else "render_export",
            mime_type="image/png",
            storage_path=f"{tenant_id}/{brand_space_id}/generated/final-render-slide-{index}.png",
            width=1080,
            height=1080,
            metadata_json={
                "render_source": "ai",
                "generation_stage": "final_render",
                "slide_index": index,
                "slide_count": 2,
                "carousel_role": "cover" if index == 1 else "detail",
                "render_overlay_scene_graph": overlay_scene_graph,
                "render_overlay_text": {
                    "headline": f"Slide {index}",
                    "body": f"Body {index}",
                    "cta": "Explore",
                    "hashtags": [],
                    "metadata": {"proof_points": [f"Point {index}"]},
                },
            },
        )
        for index in range(1, 3)
    ]
    render_calls = []

    class _RendererResponse:
        def __init__(self, slide_number: int) -> None:
            self.slide_number = slide_number

        def model_dump(self, mode: str = "json") -> dict:
            return {
                "preview_asset": {
                    "asset_id": f"preview-{self.slide_number}",
                    "asset_role": "render_preview",
                    "mime_type": "image/png",
                    "storage_path": f"{tenant_id}/{brand_space_id}/generated/overlay-preview-{self.slide_number}.png",
                    "width": 1080,
                    "height": 1080,
                },
                "export_assets": [
                    {
                        "asset_id": f"export-{self.slide_number}",
                        "asset_role": "render_export",
                        "mime_type": "image/png",
                        "storage_path": f"{tenant_id}/{brand_space_id}/generated/overlay-slide-{self.slide_number}.png",
                        "width": 1080,
                        "height": 1080,
                    }
                ],
                "renderer_metadata": {"layout_variant": "scene_graph_static"},
            }

    async def _render(payload):
        render_calls.append(payload)
        return _RendererResponse(len(render_calls))

    service.renderer = SimpleNamespace(render=_render)

    payload = await service._build_ai_final_render_overlay_payloads(
        content=content,
        assets=assets,
        explainability={"scene_graph": overlay_scene_graph, "generation_path": "image_led_social", "layout_decision": {}, "validation_report": {}},
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        selected_template_id=None,
        logo_asset_path="tenant/brand/uploads/logo.png",
        blueprint_payload=content.blueprint_payload,
        creative_decision={"layout_mode": "synthesized_layout"},
        font_asset_paths=["tenant/brand/fonts/display.ttf"],
        brand_visual_rules={"brand_name": "Jiraaf"},
    )

    assert [call.base_canvas_asset_path for call in render_calls] == [
        f"{tenant_id}/{brand_space_id}/generated/final-render-slide-1.png",
        f"{tenant_id}/{brand_space_id}/generated/final-render-slide-2.png",
    ]
    assert render_calls[0].text.headline == "Slide 1"
    assert render_calls[1].text.headline == "Slide 2"
    for index, call in enumerate(render_calls, start=1):
        text_by_role = {
            element.role: element.text
            for element in call.scene_graph.elements
            if element.element_type == "text"
        }
        assert text_by_role["headline"] == f"Slide {index}"
        assert text_by_role["body"] == f"Body {index}"
        assert "Slide headline" not in text_by_role.values()
        assert "Original support" not in text_by_role.values()
    assert payload["preview_asset"]["storage_path"].endswith("overlay-preview-1.png")
    assert [asset["storage_path"] for asset in payload["export_assets"]] == [
        f"{tenant_id}/{brand_space_id}/generated/overlay-slide-1.png",
        f"{tenant_id}/{brand_space_id}/generated/overlay-slide-2.png",
    ]
    assert payload["renderer_metadata"]["layout_variant"] == "ai_final_render_text_overlay_carousel"
    assert payload["renderer_metadata"]["render_manifest"]["base_canvas_overlay"] is True


def test_selective_overlay_text_payload_preserves_slide_body_and_empty_interior_cta() -> None:
    content = _build_content_version()
    content.generated_payload = {
        "headline": "Master weather alerts",
        "body": "Global fallback body",
        "cta": "Track local alerts",
        "hashtags": ["#Weather"],
        "metadata": {
            "carousel_slide_specs": [
                {
                    "slide_index": 1,
                    "headline": "Hook",
                    "supporting_line": "The citywide alert is only the starting point.",
                    "body": "Neighborhood sequencing changes who needs to react first.",
                    "cta": "",
                    "role": "hook",
                },
                {
                    "slide_index": 2,
                    "headline": "What most forecasts miss",
                    "supporting_line": "It is not just about rain totals.",
                    "body": "Drainage pressure and route disruption make the alert operational, not just meteorological.",
                    "cta": "",
                    "role": "detail",
                    "body_points": ["Drainage pressure matters", "Route disruption changes prioritization"],
                    "stat_highlights": ["Neighborhood-level triggers"],
                },
                {
                    "slide_index": 3,
                    "headline": "Closing",
                    "supporting_line": "Use the checklist before the next storm window.",
                    "body": "Teams can move faster when the sequence is operationalized.",
                    "cta": "Track local alerts",
                    "role": "closing",
                },
            ]
        },
    }

    payload = ContentService._selective_overlay_text_payload(
        content,
        slide_index=2,
        slide_count=3,
    )

    assert payload["body"] == "Drainage pressure and route disruption make the alert operational, not just meteorological."
    assert payload["cta"] == ""
    assert payload["metadata"]["body_points"] == [
        "Drainage pressure matters",
        "Route disruption changes prioritization",
    ]
    assert payload["metadata"]["stat_highlights"] == ["Neighborhood-level triggers"]
    assert payload["metadata"]["source"] == "structured_slide_spec"


def test_ai_final_render_overlay_text_payload_prefers_structured_slide_spec_over_fallback_asset_text() -> None:
    content = _build_content_version()
    content.generated_payload = {
        "headline": "Fallback headline",
        "body": "Fallback body",
        "cta": "Fallback CTA",
        "hashtags": ["#Weather"],
        "metadata": {
            "source": "fallback",
            "carousel_slide_specs": [
                {
                    "slide_index": 1,
                    "headline": "Structured hook",
                    "supporting_line": "Structured support",
                    "body": "Structured body copy.",
                    "cta": "",
                    "role": "hook",
                }
            ],
        },
    }
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=content.tenant_id,
        brand_space_id=content.brand_space_id,
        content_version_id=content.id,
        asset_role="render_preview",
        mime_type="image/png",
        storage_path="tenant/brand/generated/slide-1.png",
        width=1080,
        height=1080,
        metadata_json={
            "slide_index": 1,
            "slide_count": 1,
            "render_overlay_text": {
                "headline": "Fallback asset headline",
                "body": "Fallback asset body",
                "cta": "Fallback CTA",
                "hashtags": [],
                "metadata": {"source": "fallback"},
            },
        },
    )

    payload = ContentService._ai_final_render_overlay_text_payload(asset, content)

    assert payload["headline"] == "Structured hook"
    assert payload["body"] == "Structured body copy."
    assert payload["metadata"]["source"] == "structured_slide_spec"


@pytest.mark.asyncio
async def test_build_selective_ai_final_render_export_payloads_rerenders_only_targeted_slide() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    content = ContentVersion(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Sharpen slide 2 only",
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={
            "headline": "Top Bond Mistakes",
            "body": "Original body",
            "cta": "Explore",
            "hashtags": ["#bonds"],
            "metadata": {
                "carousel_slide_specs": [
                    {"slide_index": 1, "headline": "Hook", "supporting_line": "Original 1", "role": "cover"},
                    {"slide_index": 2, "headline": "Mistake 1 sharper", "supporting_line": "Updated 2", "role": "detail"},
                    {"slide_index": 3, "headline": "CTA", "supporting_line": "Original 3", "role": "cta"},
                ]
            },
        },
        blueprint_payload={
            "layout_type": "carousel",
            "zones": [{"zone_id": "headline", "role": "headline", "x": 64, "y": 64, "width": 720, "height": 180}],
            "hierarchy": ["headline"],
            "text_blocks": [],
            "image_zones": [],
            "logo_rules": {},
            "cta_placement": {},
            "platform_preset": "instagram",
            "export_format": "png",
            "overflow_strategy": {"mode": "shrink_then_wrap"},
        },
        explainability_metadata={},
    )
    overlay_scene_graph = {
        "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
        "layout_mode": "synthesized_layout",
        "confidence": 0.8,
        "layers": ["content", "brand"],
        "elements": [
            {
                "element_id": "headline",
                "element_type": "text",
                "role": "headline",
                "geometry": {"x": 0.08, "y": 0.1, "width": 0.5, "height": 0.16, "units": "normalized"},
                "text": "Slide headline",
                "style": {"font_size": 64, "fill_role": "light_text"},
            }
        ],
        "styles": {},
        "assets": [],
        "template_adaptation": {},
        "validation_hints": {},
    }
    parent_assets = [
        GeneratedAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=uuid4(),
            asset_role="render_preview" if index == 1 else "render_export",
            mime_type="image/png",
            storage_path=f"{tenant_id}/{brand_space_id}/generated/final-render-slide-{index}.png",
            width=1080,
            height=1080,
            metadata_json={
                "render_source": "ai",
                "generation_stage": "final_render",
                "slide_index": index,
                "slide_count": 3,
                "carousel_role": "cover" if index == 1 else ("detail" if index == 2 else "cta"),
                "render_overlay_scene_graph": overlay_scene_graph,
                "render_overlay_text": {
                    "headline": f"Slide {index}",
                    "body": f"Body {index}",
                    "cta": "Explore",
                    "hashtags": [],
                    "metadata": {"proof_points": [f"Point {index}"]},
                },
            },
        )
        for index in range(1, 4)
    ]
    current_assets = [
        GeneratedAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=content.id,
            asset_role="render_export",
            mime_type="image/png",
            storage_path=f"{tenant_id}/{brand_space_id}/generated/rewrite-slide-2.png",
            width=1080,
            height=1080,
            metadata_json={
                "render_source": "ai",
                "generation_stage": "final_render",
                "slide_index": 2,
                "slide_count": 3,
                "carousel_role": "detail",
            },
        )
    ]

    payload = await service._build_selective_ai_final_render_export_payloads(
        content=content,
        current_assets=current_assets,
        parent_assets=parent_assets,
        explainability={"scene_graph": overlay_scene_graph, "generation_path": "image_led_social", "layout_decision": {}, "validation_report": {}},
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        selected_template_id=None,
        logo_asset_path=None,
        blueprint_payload=content.blueprint_payload,
        creative_decision={"layout_mode": "synthesized_layout"},
        font_asset_paths=["tenant/brand/fonts/display.ttf"],
        brand_visual_rules={"brand_name": "Jiraaf"},
        regeneration_plan={"targeted_slide_indexes": [2], "reuse_slide_indexes": [1, 3]},
    )

    assert payload is not None
    assert payload["preview_asset"]["storage_path"].endswith("final-render-slide-1.png")
    assert [asset["storage_path"] for asset in payload["export_assets"]] == [
        f"{tenant_id}/{brand_space_id}/generated/final-render-slide-1.png",
        f"{tenant_id}/{brand_space_id}/generated/rewrite-slide-2.png",
        f"{tenant_id}/{brand_space_id}/generated/final-render-slide-3.png",
    ]
    assert payload["renderer_metadata"]["render_manifest"]["selective_regeneration"] is True
    assert payload["renderer_metadata"]["render_manifest"]["targeted_slide_indexes"] == [2]


def test_build_ai_logo_fallback_asset_prefers_light_logo_variant_on_dark_background() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    root = Path("tests") / f"ai-final-render-logo-variant-{uuid4()}"

    class _Storage:
        def __init__(self, base_path: Path) -> None:
            self.base_path = base_path

        def exists(self, storage_path: str) -> bool:
            return (self.base_path / storage_path).exists()

        def absolute_path(self, storage_path: str) -> str:
            return str((self.base_path / storage_path).resolve())

        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            relative = f"{category}/{filename}"
            target = self.base_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return SimpleNamespace(storage_path=relative, absolute_path=str(target.resolve()))

    service.storage = _Storage(root)

    final_render_path = f"{tenant_id}/{brand_space_id}/generated/final-render.png"
    dark_logo_path = f"{tenant_id}/{brand_space_id}/logo/jiraaf-dark.png"
    light_logo_path = f"{tenant_id}/{brand_space_id}/logo/jiraaf-light.png"
    final_render_file = root / final_render_path
    final_render_file.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (1080, 1080), (64, 48, 190, 255)).save(final_render_file, format="PNG")

    dark_logo_file = root / dark_logo_path
    dark_logo_file.parent.mkdir(parents=True, exist_ok=True)
    dark_logo = Image.new("RGBA", (500, 180), (0, 0, 0, 0))
    for x in range(120, 380):
        for y in range(60, 120):
            dark_logo.putpixel((x, y), (20, 30, 60, 255))
    dark_logo.save(dark_logo_file, format="PNG")

    light_logo_file = root / light_logo_path
    light_logo = Image.new("RGBA", (500, 180), (0, 0, 0, 0))
    for x in range(120, 380):
        for y in range(60, 120):
            light_logo.putpixel((x, y), (245, 248, 255, 255))
    light_logo.save(light_logo_file, format="PNG")

    content = ContentVersion(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a social post",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={"metadata": {"logo_position": "Top-right corner for clear brand presence with enough margin"}},
        blueprint_payload={},
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_preview",
        mime_type="image/png",
        storage_path=final_render_path,
        width=1080,
        height=1080,
        metadata_json={"render_source": "ai", "generation_stage": "final_render"},
    )

    payload = service._build_ai_logo_fallback_asset(
        content=content,
        asset=asset,
        explainability={"scene_graph": {"elements": []}, "generation_path": "ai_final_render"},
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        logo_asset_path=dark_logo_path,
        logo_asset_candidates=[
            {
                "storage_path": dark_logo_path,
                "source": "identity.logo_asset_path",
                "source_priority": 26,
                "traits": {"orientation": "horizontal", "background_variant": "light"},
                "metadata": {},
            },
            {
                "storage_path": light_logo_path,
                "source": "identity.logo_assets",
                "source_priority": 24,
                "traits": {"orientation": "horizontal", "background_variant": "dark"},
                "metadata": {},
            },
        ],
        logo_selection={
            "storage_path": dark_logo_path,
            "source": "identity.logo_asset_path",
            "source_priority": 26,
            "traits": {"orientation": "horizontal", "background_variant": "light"},
        },
    )

    assert payload is not None
    assert payload["metadata"]["logo_asset_path"] == light_logo_path
    composited_output = root / payload["storage_path"]
    with Image.open(composited_output) as rendered:
        assert rendered.getpixel((860, 90))[0] >= 220

    if root.exists():
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        root.rmdir()


def test_build_ai_logo_fallback_asset_clears_reserved_logo_zone_before_overlay() -> None:
    service = ContentService(session=None)  # type: ignore[arg-type]
    tenant_id = uuid4()
    brand_space_id = uuid4()
    root = Path("tests") / f"ai-final-render-logo-clearance-{uuid4()}"

    class _Storage:
        def __init__(self, base_path: Path) -> None:
            self.base_path = base_path

        def exists(self, storage_path: str) -> bool:
            return (self.base_path / storage_path).exists()

        def absolute_path(self, storage_path: str) -> str:
            return str((self.base_path / storage_path).resolve())

        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            relative = f"{category}/{filename}"
            target = self.base_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return SimpleNamespace(storage_path=relative, absolute_path=str(target.resolve()))

    service.storage = _Storage(root)

    final_render_path = f"{tenant_id}/{brand_space_id}/generated/final-render.png"
    logo_path = f"{tenant_id}/{brand_space_id}/logo/jiraaf.png"
    final_render_file = root / final_render_path
    final_render_file.parent.mkdir(parents=True, exist_ok=True)
    base = Image.new("RGBA", (1080, 1080), (248, 246, 238, 255))
    for x in range(1025, 1060):
        for y in range(60, 110):
            base.putpixel((x, y), (10, 30, 80, 255))
    base.save(final_render_file, format="PNG")

    logo_file = root / logo_path
    logo_file.parent.mkdir(parents=True, exist_ok=True)
    logo = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    for x in range(50, 150):
        for y in range(20, 60):
            logo.putpixel((x, y), (245, 158, 11, 255))
    logo.save(logo_file, format="PNG")

    content = ContentVersion(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Create a social post",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png"},
        generated_payload={"metadata": {"logo_position": "Top-right corner for clear brand presence with enough margin"}},
        blueprint_payload={},
        explainability_metadata={},
    )
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        content_version_id=uuid4(),
        asset_role="render_preview",
        mime_type="image/png",
        storage_path=final_render_path,
        width=1080,
        height=1080,
        metadata_json={"render_source": "ai", "generation_stage": "final_render"},
    )

    payload = service._build_ai_logo_fallback_asset(
        content=content,
        asset=asset,
        explainability={"scene_graph": {"elements": []}, "generation_path": "ai_final_render"},
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        logo_asset_path=logo_path,
    )

    assert payload is not None
    assert payload["metadata"]["logo_clearance_zone_applied"] is True
    composited_output = root / payload["storage_path"]
    with Image.open(composited_output) as rendered:
        cleared_red, cleared_green, cleared_blue, _ = rendered.getpixel((1050, 70))
        logo_red, logo_green, logo_blue, _ = rendered.getpixel((920, 90))
        assert cleared_red >= 230
        assert cleared_green >= 230
        assert cleared_blue >= 220
    assert logo_red >= 220
    assert logo_green >= 120
    assert logo_blue <= 80

    if root.exists():
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        root.rmdir()
