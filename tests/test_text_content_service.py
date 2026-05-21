from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.content import ContentSession, ContentVersion, GeneratedAsset
from app.models.knowledge import KnowledgeAsset
from app.core.exceptions import GenerationFailureError
from app.services.text_content import TextContentService


def test_text_content_service_returns_deliverable_contract_for_blog() -> None:
    contract = TextContentService._deliverable_contract("blog")
    assert contract["label"] == "blog article"
    assert "markdown article" in contract["body_instruction"]


def test_text_content_service_normalizes_payload_with_fallback_defaults() -> None:
    payload = TextContentService._normalize_payload(
        {"headline": "  Bond Basics  ", "body": "  Body copy  ", "hashtags": [" #bonds ", ""]},
        fallback={"headline": "Fallback", "body": "Fallback body", "cta": "", "hashtags": [], "metadata": {}},
        deliverable_type="linkedin_post",
    )
    assert payload["headline"] == "Bond Basics"
    assert payload["body"] == "Body copy"
    assert payload["hashtags"] == ["#bonds"]


def test_text_content_service_builds_revision_scope_instruction() -> None:
    instruction = TextContentService._revision_scope_instruction(
        {
            "targeted_fields": ["cta"],
            "slide_indexes": [3],
            "preserve_visuals": True,
            "only_targeted": True,
        }
    )
    assert "cta" in instruction.lower()
    assert "slide 3" in instruction.lower()
    assert "preserve the existing visual framing" in instruction.lower()
    assert "do not broaden the rewrite" in instruction.lower()


def test_text_content_service_apply_revision_scope_preserves_untargeted_fields() -> None:
    original_payload = {
        "deliverable_type": "linkedin_post",
        "headline": "Original headline",
        "body": "Original body",
        "cta": "Original CTA",
        "hashtags": ["#jiraaf"],
        "metadata": {"hook_type": "question", "sources_used": ["brief"]},
    }
    rewritten_payload = {
        "deliverable_type": "linkedin_post",
        "headline": "New headline",
        "body": "New body",
        "cta": "Updated CTA",
        "hashtags": ["#new"],
        "metadata": {"hook_type": "stat"},
    }

    merged = TextContentService._apply_revision_scope_to_payload(
        original_payload=original_payload,
        rewritten_payload=rewritten_payload,
        revision_scope={"targeted_fields": ["cta"], "only_targeted": True},
    )

    assert merged["headline"] == "Original headline"
    assert merged["body"] == "Original body"
    assert merged["cta"] == "Updated CTA"
    assert merged["hashtags"] == ["#jiraaf"]
    assert merged["metadata"] == {"hook_type": "question", "sources_used": ["brief"]}


def test_text_content_service_apply_revision_scope_preserves_copy_for_layout_only_edits() -> None:
    original_payload = {
        "deliverable_type": "linkedin_post",
        "headline": "Original headline",
        "body": "Original body",
        "cta": "Original CTA",
        "hashtags": ["#jiraaf"],
        "metadata": {"hook_type": "question", "sources_used": ["brief"]},
    }
    rewritten_payload = {
        "deliverable_type": "linkedin_post",
        "headline": "Changed headline",
        "body": "Changed body",
        "cta": "Changed CTA",
        "hashtags": ["#new"],
        "metadata": {"hook_type": "stat"},
    }

    merged = TextContentService._apply_revision_scope_to_payload(
        original_payload=original_payload,
        rewritten_payload=rewritten_payload,
        revision_scope={"preserve_copy": True, "change_layout": True},
    )

    assert merged["headline"] == "Original headline"
    assert merged["body"] == "Original body"
    assert merged["cta"] == "Original CTA"
    assert merged["hashtags"] == ["#jiraaf"]
    assert merged["metadata"] == {"hook_type": "question", "sources_used": ["brief"]}


def test_text_content_service_assert_research_guard_raises_when_hard_fail_is_required() -> None:
    with pytest.raises(GenerationFailureError) as exc_info:
        TextContentService._assert_research_guard(
            prompt="Analyze the latest FTA with exact strategic implications.",
            brief={"research_guard": {"hard_fail": True, "reason": "Missing verified sources."}},
            stage="text.generate",
        )

    assert exc_info.value.reason_code == "research_backing_required"


def test_text_content_service_assert_not_model_fallback_raises() -> None:
    with pytest.raises(GenerationFailureError) as exc_info:
        TextContentService._assert_not_model_fallback(
            prompt="Write a LinkedIn post on bond duration.",
            normalized_payload={
                "headline": "Write a LinkedIn post on bond duration.",
                "body": "",
                "cta": "",
                "hashtags": [],
                "metadata": {"source": "fallback"},
            },
            deliverable_type="linkedin_post",
            previous_output=None,
            stage="text.generate_payload",
        )

    assert exc_info.value.reason_code == "text_generation_fallback"


def test_text_content_service_generate_payload_includes_content_plan_guidance() -> None:
    service = TextContentService.__new__(TextContentService)

    class _Provider:
        def __init__(self) -> None:
            self.envelope = None

        def generate_structured_json(self, envelope, fallback):  # noqa: ANN001, ANN201
            self.envelope = envelope
            return {
                "deliverable_type": "linkedin_post",
                "headline": "Why rates matter",
                "body": "Bond yields changed the decision context for investors.",
                "cta": "Learn more",
                "hashtags": ["#Bonds"],
                "metadata": {"hook_type": "insight"},
            }

    provider = _Provider()
    service.providers = SimpleNamespace(get_text_provider=lambda _mode: provider)
    service.research_editorial = SimpleNamespace(enforce_source_backing=lambda payload, **_kwargs: payload)

    payload = service._generate_payload(
        prompt="Write a LinkedIn post about interest-rate moves.",
        brand_context={"brand_name": "Jiraaf"},
        persona_context={"name": "Fixed-income investor"},
        objective_context={"name": "Education"},
        deliverable_type="linkedin_post",
        session_memory={"follow_up_intent": {"mode": "fresh_generation"}},
        knowledge_brief=[],
        live_research={},
        research_editorial_brief={"thesis": "Rates shift the entry-point conversation."},
        format_family_plan={"content_structure": "hook_then_explain"},
        content_plan={"ordered_sections": ["Hook", "What changed", "Investor takeaway"]},
        uses_previous_output=False,
        previous_output=None,
        revision_scope=None,
    )

    assert payload["headline"] == "Why rates matter"
    assert provider.envelope is not None
    assert "Content plan:" in provider.envelope.user
    assert "ordered_sections" in provider.envelope.user
    assert "Treat Content plan as the authoritative narrative plan" in provider.envelope.user


@pytest.mark.asyncio
async def test_text_content_service_evaluate_returns_scorecard_summary() -> None:
    service = TextContentService.__new__(TextContentService)
    service.brands = SimpleNamespace(get_scoped=lambda tenant_id, brand_space_id: None)

    async def _brand(*args, **kwargs):
        return SimpleNamespace(resolved_brand_context={"voice_tone": {}}, lifecycle_state="active")

    async def _personas(*args, **kwargs):
        return []

    async def _objectives(*args, **kwargs):
        return []

    service.brands = SimpleNamespace(get_scoped=_brand)
    service.personas = SimpleNamespace(list_by_brand=_personas)
    service.objectives = SimpleNamespace(list_by_brand=_objectives)
    service.content = SimpleNamespace()
    service.tone = SimpleNamespace(
        evaluate=lambda **kwargs: {
            "score": 82,
            "matched_signals": ["Specific phrasing"],
            "deviations": ["CTA is weak"],
            "rewrite_suggestions": ["Sharpen the close"],
            "quality_summary": ["Strong brand fit overall."],
            "field_guidance": {"headline": ["Keep the hook tighter"]},
            "persuasion_dimensions": {
                "brand_alignment": 88,
                "clarity": 80,
                "proof_strength": 76,
                "objection_handling": 72,
                "cta_strength": 68,
            },
        }
    )
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={"last_text_output": "Previous content body"},
        is_active=True,
    )

    report = await TextContentService.evaluate(
        service,
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session=session,
        prompt="Check tone consistency",
    )

    assert report["mode"] == "evaluation"
    assert report["scorecard"]["overall_score"] == 82
    assert report["scorecard"]["brand_alignment_score"] == 88
    assert report["artifact_state"]["evaluation_history"][0]["overall_score"] == 82
    assert "Tone score: 82/100" in report["summary"]


@pytest.mark.asyncio
async def test_text_content_service_evaluate_uses_referenced_asset_content_when_prompt_has_no_text() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    asset_id = uuid4()
    linked_content_id = uuid4()
    service = TextContentService.__new__(TextContentService)

    async def _brand(*args, **kwargs):
        return SimpleNamespace(resolved_brand_context={"voice_tone": {}}, lifecycle_state="active")

    async def _personas(*args, **kwargs):
        return []

    async def _objectives(*args, **kwargs):
        return []

    async def _get_generated_asset(requested_asset_id, requested_tenant_id, requested_brand_space_id):
        assert requested_asset_id == asset_id
        assert requested_tenant_id == tenant_id
        assert requested_brand_space_id == brand_space_id
        return GeneratedAsset(
            id=asset_id,
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=linked_content_id,
            asset_role="render_preview",
            mime_type="image/png",
            storage_path="tenant/brand/generated/preview.png",
            metadata_json={},
        )

    async def _get_content(content_id, requested_tenant_id, requested_brand_space_id):
        assert content_id == linked_content_id
        assert requested_tenant_id == tenant_id
        assert requested_brand_space_id == brand_space_id
        return ContentVersion(
            id=linked_content_id,
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            session_id=uuid4(),
            created_by=uuid4(),
            prompt="Write a post",
            generated_payload={"headline": "Headline", "body": "Body copy from asset", "cta": "CTA"},
            blueprint_payload={},
            explainability_metadata={},
            tone_feedback={},
        )

    service.brands = SimpleNamespace(get_scoped=_brand)
    service.personas = SimpleNamespace(list_by_brand=_personas)
    service.objectives = SimpleNamespace(list_by_brand=_objectives)
    service.assets = SimpleNamespace(get_scoped=_get_generated_asset)
    service.contents = SimpleNamespace(get_scoped=_get_content)
    service.knowledge_assets = SimpleNamespace(get_scoped=AsyncMock(return_value=None))
    service.tone = SimpleNamespace(
        evaluate=lambda **kwargs: {
            "score": 75,
            "matched_signals": ["Used asset-backed content"],
            "deviations": [],
            "rewrite_suggestions": [],
            "quality_summary": [],
            "field_guidance": {},
            "persuasion_dimensions": {
                "brand_alignment": 74,
                "clarity": 76,
                "proof_strength": 72,
                "objection_handling": 70,
                "cta_strength": 73,
            },
        }
    )
    session = ContentSession(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={},
        is_active=True,
    )

    report = await TextContentService.evaluate(
        service,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session=session,
        prompt="Check tone consistency",
        reference_asset_ids=[asset_id],
    )

    assert "Body copy from asset" in report["reviewed_content"]
    assert report["artifact_state"]["source_linked_artifacts"]["reviewed_asset_ids"] == [str(asset_id)]
    assert report["reviewed_asset_ids"] == [str(asset_id)]
    assert report["review_sources"][0]["source_type"] == "generated_asset"


@pytest.mark.asyncio
async def test_text_content_service_evaluate_reports_uploaded_asset_diagnostics() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    asset_id = uuid4()
    service = TextContentService.__new__(TextContentService)

    async def _brand(*args, **kwargs):
        return SimpleNamespace(resolved_brand_context={"voice_tone": {}}, lifecycle_state="active")

    async def _personas(*args, **kwargs):
        return []

    async def _objectives(*args, **kwargs):
        return []

    async def _missing_generated(*args, **kwargs):
        return None

    async def _knowledge(requested_asset_id, requested_tenant_id, requested_brand_space_id):
        assert requested_asset_id == asset_id
        assert requested_tenant_id == tenant_id
        assert requested_brand_space_id == brand_space_id
        return KnowledgeAsset(
            id=asset_id,
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            name="Uploaded deck",
            original_filename="deck.pdf",
            mime_type="application/pdf",
            storage_path="tenant/brand/uploads/deck.pdf",
            extracted_summary="Structured summary from uploaded document.",
            metadata_json={},
            structured_data_json={"analysis_quality": {"summary_quality_score": 7.5, "ocr_signal_score": 6.0, "observed_signal_types": ["layout", "typography"]}},
            normalized_data_json={},
            validation_summary_json={"warnings": ["Using summary-level extraction instead of full OCR text."]},
            validation_state="warning",
            page_count=7,
        )

    service.brands = SimpleNamespace(get_scoped=_brand)
    service.personas = SimpleNamespace(list_by_brand=_personas)
    service.objectives = SimpleNamespace(list_by_brand=_objectives)
    service.assets = SimpleNamespace(get_scoped=_missing_generated)
    service.contents = SimpleNamespace(get_scoped=AsyncMock(return_value=None))
    service.knowledge_assets = SimpleNamespace(get_scoped=_knowledge)
    service.storage = SimpleNamespace(exists=lambda path: True, absolute_path=lambda path: "C:\\tmp\\uploaded-deck.pdf")
    service.ocr = SimpleNamespace(
        extract=lambda path: {
            "text": "Structured OCR text from uploaded document",
            "images": ["C:\\tmp\\uploaded-page1.png"] if path.endswith(".pdf") else [path],
            "page_count": 1,
            "source_format": "pdf" if path.endswith(".pdf") else "png",
            "analysis_path": "",
            "warnings": [],
        }
    )
    service.tone = SimpleNamespace(
        evaluate=lambda **kwargs: {
            "score": 78,
            "matched_signals": ["Clear summary"],
            "deviations": ["Needs sharper proof"],
            "rewrite_suggestions": ["Add a stronger data point"],
            "quality_summary": [],
            "field_guidance": {},
            "persuasion_dimensions": {
                "brand_alignment": 79,
                "clarity": 80,
                "proof_strength": 70,
                "objection_handling": 74,
                "cta_strength": 68,
            },
        }
    )
    session = ContentSession(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={},
        is_active=True,
    )

    report = await TextContentService.evaluate(
        service,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session=session,
        prompt="Check tone consistency",
        reference_asset_ids=[asset_id],
    )

    assert report["evaluation_scope"] == "visual_asset_backed"
    assert report["review_type"] == "asset_tone_brand_consistency"
    assert report["scorecard"]["asset_coverage_score"] == 0
    assert report["scorecard"]["document_structure_score"] > 0
    assert report["scorecard"]["source_quality_score"] >= 0
    assert report["review_sources"][0]["extraction_method"] == "extracted_summary"
    assert report["review_sources"][0]["asset_kind"] == "document"
    assert report["review_sources"][0]["review_workflow"] == "visual_first"
    assert report["asset_diagnostics"]["document_count"] == 1
    assert "ocr_confidence_score" in report["asset_diagnostics"]
    assert "summary-level extraction" in report["asset_gaps"][0]


@pytest.mark.asyncio
async def test_text_content_service_evaluate_builds_visual_review_for_generated_image_asset() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    asset_id = uuid4()
    linked_content_id = uuid4()
    service = TextContentService.__new__(TextContentService)

    async def _brand(*args, **kwargs):
        return SimpleNamespace(
            resolved_brand_context={
                "brand_name": "Jiraaf",
                "visual_identity": {"palette": [{"hex_code": "#FF9900"}]},
            },
            lifecycle_state="active",
        )

    async def _personas(*args, **kwargs):
        return []

    async def _objectives(*args, **kwargs):
        return []

    async def _get_generated_asset(requested_asset_id, requested_tenant_id, requested_brand_space_id):
        return GeneratedAsset(
            id=requested_asset_id,
            tenant_id=requested_tenant_id,
            brand_space_id=requested_brand_space_id,
            content_version_id=linked_content_id,
            asset_role="render_preview",
            mime_type="image/png",
            storage_path="tenant/brand/generated/preview.png",
            metadata_json={"render_source": "ai"},
            width=1080,
            height=1080,
        )

    async def _get_content(content_id, requested_tenant_id, requested_brand_space_id):
        return ContentVersion(
            id=content_id,
            tenant_id=requested_tenant_id,
            brand_space_id=requested_brand_space_id,
            session_id=uuid4(),
            created_by=uuid4(),
            prompt="Generate a LinkedIn image on bond investing mistakes for Jiraaf",
            generated_payload={"headline": "Bond mistakes", "body": "Avoid these mistakes", "cta": "Explore Jiraaf"},
            blueprint_payload={},
            explainability_metadata={},
            tone_feedback={},
        )

    service.brands = SimpleNamespace(get_scoped=_brand)
    service.personas = SimpleNamespace(list_by_brand=_personas)
    service.objectives = SimpleNamespace(list_by_brand=_objectives)
    service.assets = SimpleNamespace(get_scoped=_get_generated_asset)
    service.contents = SimpleNamespace(get_scoped=_get_content)
    service.knowledge_assets = SimpleNamespace(get_scoped=AsyncMock(return_value=None))
    service.storage = SimpleNamespace(exists=lambda path: True, absolute_path=lambda path: "C:\\tmp\\preview.png")
    service.ocr = SimpleNamespace(
        extract=lambda path: {
            "text": "Avoid bond investing mistakes with Jiraaf",
            "images": [path],
            "page_count": 1,
            "source_format": "png",
            "analysis_path": "",
            "warnings": [],
        }
    )
    service.tone = SimpleNamespace(
        evaluate=lambda **kwargs: {
            "score": 83,
            "matched_signals": ["Clear hook"],
            "deviations": [],
            "rewrite_suggestions": [],
            "quality_summary": [],
            "field_guidance": {},
            "persuasion_dimensions": {
                "brand_alignment": 84,
                "clarity": 82,
                "proof_strength": 78,
                "objection_handling": 75,
                "cta_strength": 80,
            },
        }
    )
    session = ContentSession(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={},
        is_active=True,
    )

    report = await TextContentService.evaluate(
        service,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session=session,
        prompt="Check if this image matches the original prompt",
        reference_asset_ids=[asset_id],
    )

    assert report["visual_review_report"]["asset_count"] == 1
    assert report["visual_review_report"]["page_count"] == 1
    assert report["visual_review_report"]["prompt_alignment_score"] > 0
    assert "hierarchy_score" in report["visual_review_report"]
    assert "crowding_score" in report["visual_review_report"]
    assert "ocr_confidence_score" in report["visual_review_report"]
    assert report["scorecard"]["visual_diagnostic_score"] > 0
    assert "hierarchy_score" in report["scorecard"]
    assert report["scorecard"]["ocr_confidence_score"] > 0
    assert report["review_sources"][0]["visual_review"]["page_reviews"][0]["prompt_alignment_score"] > 0
    assert "page_findings" in report["review_sources"][0]["visual_review"]["page_reviews"][0]
    assert "region_diagnostics" in report["review_sources"][0]["visual_review"]["page_reviews"][0]


@pytest.mark.asyncio
async def test_text_content_service_evaluate_builds_page_reviews_for_uploaded_document() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    asset_id = uuid4()
    service = TextContentService.__new__(TextContentService)

    async def _brand(*args, **kwargs):
        return SimpleNamespace(
            resolved_brand_context={"brand_name": "Jiraaf"},
            lifecycle_state="active",
        )

    async def _personas(*args, **kwargs):
        return []

    async def _objectives(*args, **kwargs):
        return []

    async def _missing_generated(*args, **kwargs):
        return None

    async def _knowledge(requested_asset_id, requested_tenant_id, requested_brand_space_id):
        return KnowledgeAsset(
            id=requested_asset_id,
            tenant_id=requested_tenant_id,
            brand_space_id=requested_brand_space_id,
            name="FTA deck",
            original_filename="fta.pdf",
            mime_type="application/pdf",
            storage_path="tenant/brand/uploads/fta.pdf",
            extracted_summary="FTA summary.",
            metadata_json={},
            structured_data_json={},
            normalized_data_json={},
            validation_summary_json={},
            validation_state="valid",
            page_count=2,
        )

    service.brands = SimpleNamespace(get_scoped=_brand)
    service.personas = SimpleNamespace(list_by_brand=_personas)
    service.objectives = SimpleNamespace(list_by_brand=_objectives)
    service.assets = SimpleNamespace(get_scoped=_missing_generated)
    service.contents = SimpleNamespace(get_scoped=AsyncMock(return_value=None))
    service.knowledge_assets = SimpleNamespace(get_scoped=_knowledge)
    service.storage = SimpleNamespace(exists=lambda path: True, absolute_path=lambda path: "C:\\tmp\\fta.pdf")
    service.ocr = SimpleNamespace(
        extract=lambda path: {
            "text": "India New Zealand FTA analysis",
            "images": ["C:\\tmp\\page1.png", "C:\\tmp\\page2.png"] if path.endswith(".pdf") else [path],
            "page_count": 2 if path.endswith(".pdf") else 1,
            "source_format": "pdf" if path.endswith(".pdf") else "png",
            "analysis_path": "",
            "warnings": [],
        }
    )
    service.tone = SimpleNamespace(
        evaluate=lambda **kwargs: {
            "score": 80,
            "matched_signals": ["Analytical framing"],
            "deviations": [],
            "rewrite_suggestions": [],
            "quality_summary": [],
            "field_guidance": {},
            "persuasion_dimensions": {
                "brand_alignment": 80,
                "clarity": 81,
                "proof_strength": 76,
                "objection_handling": 74,
                "cta_strength": 70,
            },
        }
    )
    session = ContentSession(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "pdf"},
        conversational_context={},
        is_active=True,
    )

    report = await TextContentService.evaluate(
        service,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session=session,
        prompt="Check whether this deck matches the prompt about the India New Zealand FTA",
        reference_asset_ids=[asset_id],
    )

    assert report["visual_review_report"]["asset_count"] == 1
    assert report["visual_review_report"]["page_count"] == 2
    assert len(report["visual_review_report"]["page_reviews"]) == 2
    assert report["visual_review_report"]["document_segments"]
    assert report["visual_review_report"]["region_overview"]["dominant_regions"]
    assert "page_balance_score" in report["visual_review_report"]
    assert "hierarchy_score" in report["asset_diagnostics"]
    assert report["evaluation_scope"] == "visual_asset_backed"
    assert report["asset_diagnostics"]["document_count"] == 1
    assert report["review_sources"][0]["visual_review"]["document_segments"][0]["page_index"] == 1
    assert "ocr_confidence_score" in report["review_sources"][0]["visual_review"]["page_reviews"][0]
