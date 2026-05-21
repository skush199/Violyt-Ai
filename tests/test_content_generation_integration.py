from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai.contracts import (
    AIOrchestrationResponse,
    BlueprintPayload,
    CreativeDecisionPayload,
    GeneratedImageAsset,
    GenerationSceneGraph,
    MessageStrategyPayload,
    SceneGraphValidationReport,
    StructuredTextPayload,
)
from app.core.exceptions import GenerationFailureError, LifecycleError, NotFoundError
from app.core.enums import AssetRole, BrandSpaceLifecycle, ContentLifecycle, UsageMetricCode
from app.models.content import GeneratedAsset
from app.schemas.common import StudioPanelSelection
from app.schemas.content import ContentGenerateRequest, ContentRewriteRequest, RequestInheritancePolicy, ToneCheckRequest
from app.services.content import ContentService


class _DummyAsyncSession:
    def __init__(self) -> None:
        self.deleted = []
        self.commit_count = 0
        self.added = []

    async def commit(self) -> None:
        self.commit_count += 1
        return None

    async def flush(self) -> None:
        return None

    async def refresh(self, _item) -> None:
        return None

    async def delete(self, item) -> None:
        self.deleted.append(item)

    def add(self, item) -> None:
        self.added.append(item)

    async def get(self, _model, _entity_id):
        return None

    async def execute(self, *_args, **_kwargs):
        return _DummyResult()


class _DummyResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None


class _CaptureOrchestrator:
    def __init__(self, response: AIOrchestrationResponse) -> None:
        self.request = None
        self.response = response

    def generate(self, request):
        self.request = request
        return self.response


class _AsyncCollector:
    def __init__(self) -> None:
        self.items = []

    async def add(self, item) -> None:
        self.items.append(item)


class _CaptureTextProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.envelope = None
        self.fallback = None

    def generate_structured_json(self, envelope, fallback):  # noqa: ANN001, ANN201
        self.envelope = envelope
        self.fallback = fallback
        return dict(self.payload)


def test_content_rewrite_compiled_context_backfills_visual_plan_into_stored_context() -> None:
    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    service.orchestrator = SimpleNamespace(
        compiler=SimpleNamespace(
            _content_format_brief=lambda _guide, _panel: {"format": "carousel"},
        )
    )
    original = SimpleNamespace(
        explainability_metadata={
            "compiled_context": {
                "content_format_brief": {"format": "carousel"},
                "research_editorial_brief": {"thesis": "Distinct frames teach distinct ideas."},
                "format_family_plan": {"content_structure": "carousel"},
            }
        }
    )

    compiled = service._rewrite_compiled_context(
        original=original,
        source_prompt="Rewrite the carousel with clearer sequencing.",
        resolved_brand_context={"brand_name": "Jiraaf"},
        persona_context={"name": "Investor"},
        objective_context={"name": "Education"},
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png"},
        session=None,
        content_format_guide={"summary": "Keep slides distinct."},
        research_editorial_brief={"thesis": "Distinct frames teach distinct ideas."},
        format_family_plan={"content_structure": "carousel"},
        visual_plan={"slide_flow": ["hook", "explain", "implication"]},
    )

    assert compiled["visual_plan"] == {"slide_flow": ["hook", "explain", "implication"]}


def test_content_rewrite_compiled_context_backfills_content_plan_into_stored_context() -> None:
    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    service.orchestrator = SimpleNamespace(
        compiler=SimpleNamespace(
            _content_format_brief=lambda _guide, _panel: {"format": "carousel"},
        )
    )
    original = SimpleNamespace(
        explainability_metadata={
            "compiled_context": {
                "content_format_brief": {"format": "carousel"},
                "research_editorial_brief": {"thesis": "Distinct frames teach distinct ideas."},
                "format_family_plan": {"content_structure": "carousel"},
            }
        }
    )

    compiled = service._rewrite_compiled_context(
        original=original,
        source_prompt="Rewrite the carousel with clearer sequencing.",
        resolved_brand_context={"brand_name": "Jiraaf"},
        persona_context={"name": "Investor"},
        objective_context={"name": "Education"},
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png"},
        session=None,
        content_format_guide={"summary": "Keep slides distinct."},
        research_editorial_brief={"thesis": "Distinct frames teach distinct ideas."},
        format_family_plan={"content_structure": "carousel"},
        content_plan={"sequence_contract": "native_carousel_metadata", "slides": [{"title": "Hook"}]},
        visual_plan={"slide_flow": ["hook", "explain", "implication"]},
    )

    assert compiled["content_plan"] == {
        "sequence_contract": "native_carousel_metadata",
        "slides": [{"title": "Hook"}],
    }


def test_content_rewrite_compiled_context_passes_visual_plan_to_compiler_when_rebuilding() -> None:
    captured: dict[str, object] = {}
    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    service.orchestrator = SimpleNamespace(
        compiler=SimpleNamespace(
            compile=lambda **kwargs: captured.update(kwargs) or {"compiled": True},
            _content_format_brief=lambda _guide, _panel: {"format": "carousel"},
        )
    )
    original = SimpleNamespace(explainability_metadata={})

    compiled = service._rewrite_compiled_context(
        original=original,
        source_prompt="Rewrite the carousel with clearer sequencing.",
        resolved_brand_context={"brand_name": "Jiraaf"},
        persona_context={"name": "Investor"},
        objective_context={"name": "Education"},
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png"},
        session=None,
        content_format_guide={"summary": "Keep slides distinct."},
        research_editorial_brief={"thesis": "Distinct frames teach distinct ideas."},
        format_family_plan={"content_structure": "carousel"},
        visual_plan={"slide_flow": ["hook", "explain", "implication"]},
    )

    assert compiled == {"compiled": True}
    assert captured["visual_plan"] == {"slide_flow": ["hook", "explain", "implication"]}


def test_content_rewrite_compiled_context_passes_content_plan_to_compiler_when_rebuilding() -> None:
    captured: dict[str, object] = {}
    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    service.orchestrator = SimpleNamespace(
        compiler=SimpleNamespace(
            compile=lambda **kwargs: captured.update(kwargs) or {"compiled": True},
            _content_format_brief=lambda _guide, _panel: {"format": "carousel"},
        )
    )
    original = SimpleNamespace(explainability_metadata={})

    compiled = service._rewrite_compiled_context(
        original=original,
        source_prompt="Rewrite the carousel with clearer sequencing.",
        resolved_brand_context={"brand_name": "Jiraaf"},
        persona_context={"name": "Investor"},
        objective_context={"name": "Education"},
        studio_panel={"format": "carousel", "platform_preset": "instagram", "file_type": "png"},
        session=None,
        content_format_guide={"summary": "Keep slides distinct."},
        research_editorial_brief={"thesis": "Distinct frames teach distinct ideas."},
        format_family_plan={"content_structure": "carousel"},
        content_plan={"sequence_contract": "native_carousel_metadata", "slides": [{"title": "Hook"}]},
        visual_plan={"slide_flow": ["hook", "explain", "implication"]},
    )

    assert compiled == {"compiled": True}
    assert captured["content_plan"] == {
        "sequence_contract": "native_carousel_metadata",
        "slides": [{"title": "Hook"}],
    }


@pytest.mark.asyncio
async def test_content_generate_passes_seeded_brandspace_context_to_orchestrator() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    user_id = uuid4()
    persona_id = uuid4()
    objective_id = uuid4()
    request_asset_id = uuid4()
    session_id = uuid4()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    brand = SimpleNamespace(
        id=brand_space_id,
        tenant_id=tenant_id,
        name="Jiraaf",
        lifecycle_state=BrandSpaceLifecycle.ACTIVE,
        resolved_brand_context={
            "brand_name": "Jiraaf",
            "identity": {"logo_assets": []},
            "visual_identity": {
                "brand_color_palette": {"primary": "#003975", "secondary": "#FFA400", "accent": "#00CB91"},
            },
        },
    )
    persona = SimpleNamespace(
        id=persona_id,
        is_default=True,
        name="Young professional",
        role="traveler",
        psychographics={},
        demographics={},
        audience_goals=["Save on flights"],
        motivations=["Travel more"],
        fears_and_pain_points=["Overpaying"],
        objections=[],
        content_behavior={},
        language_preference="en",
    )
    objective = SimpleNamespace(
        id=objective_id,
        is_default=True,
        name="Travel acquisition",
        description="Drive consideration for smarter travel planning",
        content_type="social",
        platform_scope=["instagram"],
        configuration={},
    )
    session = SimpleNamespace(id=session_id, conversational_context={"message_count": 6})

    final_render_asset = GeneratedImageAsset(
        asset_id=uuid4(),
        mime_type="image/png",
        storage_path="tenant/brand/generated/final-render.png",
        width=1080,
        height=1080,
        asset_role="render_preview",
        metadata={"render_source": "ai"},
    )
    response = AIOrchestrationResponse(
        message_strategy=MessageStrategyPayload(primary_campaign_theme="Affordable travel confidence"),
        text=StructuredTextPayload(
            headline="Book Flights Smarter",
            body="Compare fares, stay flexible, and save more on every trip.",
            cta="Explore more",
            hashtags=["#Travel"],
            metadata={"proof_points": ["Compare fares", "Stay flexible"]},
        ),
        creative_decision=CreativeDecisionPayload(
            layout_mode="synthesized_layout",
            confidence=0.87,
            asset_strategy={"logo_variant": "horizontal"},
        ),
        scene_graph=GenerationSceneGraph.model_validate(
            {
                "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                "layout_mode": "synthesized_layout",
                "confidence": 0.87,
                "layers": ["background", "content"],
                "elements": [
                    {"element_id": "headline", "element_type": "text", "role": "headline", "geometry": {"x": 0.08, "y": 0.1, "width": 0.6, "height": 0.16}, "text": "Book Flights Smarter"},
                    {"element_id": "image", "element_type": "image", "role": "image", "geometry": {"x": 0.52, "y": 0.14, "width": 0.34, "height": 0.42}},
                    {"element_id": "proof_points", "element_type": "text", "role": "proof_points", "geometry": {"x": 0.08, "y": 0.34, "width": 0.38, "height": 0.18}, "text": ["Compare fares", "Stay flexible"]},
                    {"element_id": "cta", "element_type": "text", "role": "cta", "geometry": {"x": 0.08, "y": 0.82, "width": 0.28, "height": 0.08}, "text": "Explore more"},
                ],
                "styles": {"layout_archetype": "wide_editorial_split"},
                "assets": [],
                "template_adaptation": {},
                "validation_hints": {},
            }
        ),
        validation_report=SceneGraphValidationReport(status="clean"),
        repair_attempts=1,
        blueprint=BlueprintPayload(
            layout_type="single-panel",
            zones=[],
            hierarchy=["headline", "image", "proof_points", "cta"],
            text_blocks=[],
            image_zones=[],
            logo_rules={},
            cta_placement={},
            platform_preset="instagram",
            export_format="png",
            overflow_strategy={"mode": "shrink_then_wrap"},
        ),
        image_assets=[],
        final_render_asset=final_render_asset,
        render_authority="ai",
        explainability={
            "selected_reference_images": [
                {
                    "asset_id": str(request_asset_id),
                    "asset_role": "reference_creative",
                    "storage_path": "tenant/brand/reference/request-flight.png",
                    "mime_type": "image/png",
                    "trust_level": "trusted",
                }
            ]
        },
        tone_analysis={"score": 0.91, "summary": "on-brand"},
    )
    orchestrator = _CaptureOrchestrator(response)
    saved_contents = _AsyncCollector()
    saved_assets = _AsyncCollector()

    service.orchestrator = orchestrator
    service.contents = saved_contents
    service.assets = saved_assets
    service.content_format_guide = SimpleNamespace(
        load=lambda: {
            "summary": "Instagram static should stay decisive and scan-friendly.",
            "rules": {"static": ["One clear message per frame."]},
            "source_path": "docs/Content Formats Guide.docx",
        }
    )
    service.trace = SimpleNamespace(start_trace=lambda **kwargs: {"trace_id": "trace-1"}, write_payload=lambda *args, **kwargs: None)
    service.validator = SimpleNamespace(refresh_brand_context=lambda brand_space_id: None)

    async def _refresh_brand_context(_brand_space_id):
        return brand, {}

    async def _gather_context(_brand_space_id):
        return {"brand": brand, "sections": [], "personas": [persona], "objectives": [objective]}

    async def _get_or_create_session(*args, **kwargs):
        return session

    async def _build_session_memory(**kwargs):
        return {
            "follow_up_intent": {"mode": "variant_of_previous", "uses_previous_output": True},
            "latest_content_version": {
                "id": str(uuid4()),
                "headline": "Earlier travel post",
                "scene_graph": {"styles": {"layout_archetype": "editorial_stack"}},
            },
        }

    async def _resolve_request_reference_assets(*args, **kwargs):
        return [
            {
                "asset_id": str(request_asset_id),
                "asset_role": "reference_creative",
                "storage_path": "tenant/brand/reference/request-flight.png",
                "mime_type": "image/png",
                "trust_level": "trusted",
            }
        ]

    async def _resolve_brand_reference_assets(*args, **kwargs):
        return [
            {
                "asset_id": str(uuid4()),
                "asset_role": "reference_creative",
                "storage_path": "tenant/brand/reference/brand-moodboard.png",
                "mime_type": "image/png",
                "trust_level": "trusted",
            }
        ]

    async def _resolve_generation_decision(**kwargs):
        return {"mode": "synthesized_layout", "asset_strategy": {"dominant_visual_system": "generated_image"}}

    async def _collect_logo_asset_candidates(*args, **kwargs):
        return [
            {"storage_path": "tenant/brand/logo/jiraaf-horizontal-dark.png", "traits": {"orientation": "horizontal", "background_variant": "light"}},
            {"storage_path": "tenant/brand/logo/jiraaf-stacked-light.png", "traits": {"orientation": "stacked", "background_variant": "dark"}},
        ]

    async def _resolve_logo_asset_selection(*args, **kwargs):
        return {"storage_path": "tenant/brand/logo/jiraaf-horizontal-dark.png", "traits": {"orientation": "horizontal", "background_variant": "light"}}

    async def _build_retrieved_knowledge(*args, **kwargs):
        return {"brand": [{"content": "Trusted travel platform"}]}, {"brand": {"count": 1}}

    async def _record_session_context(*args, **kwargs):
        return None

    service.validator = SimpleNamespace(refresh_brand_context=_refresh_brand_context)
    service._gather_context = _gather_context
    service._get_or_create_session = _get_or_create_session
    service._build_session_memory = _build_session_memory
    service._resolve_request_reference_assets = _resolve_request_reference_assets
    service._resolve_brand_reference_assets = _resolve_brand_reference_assets
    service._resolve_generation_decision = _resolve_generation_decision
    service._collect_logo_asset_candidates = _collect_logo_asset_candidates
    service._resolve_logo_asset_selection = _resolve_logo_asset_selection
    service._build_retrieved_knowledge = _build_retrieved_knowledge
    service._record_session_context = _record_session_context
    service.template_service = SimpleNamespace(recommend=lambda **kwargs: [])
    service.templates = SimpleNamespace(get_scoped=lambda *args, **kwargs: None)
    service.template_metadata = SimpleNamespace(get_by_template=lambda *args, **kwargs: None)
    service.usage = SimpleNamespace(enforce=lambda *args, **kwargs: None, increment=lambda *args, **kwargs: None)

    async def _recommend(**kwargs):
        return []

    async def _get_template(*args, **kwargs):
        return None

    async def _get_template_meta(*args, **kwargs):
        return None

    async def _enforce(*args, **kwargs):
        return None

    async def _increment(*args, **kwargs):
        return None

    service.template_service = SimpleNamespace(recommend=_recommend)
    service.templates = SimpleNamespace(get_scoped=_get_template)
    service.template_metadata = SimpleNamespace(get_by_template=_get_template_meta)
    service.usage = SimpleNamespace(enforce=_enforce, increment=_increment)

    payload = ContentGenerateRequest(
        prompt="Regenerate this with a different layout.",
        studio_panel=StudioPanelSelection(
            platform_preset="instagram",
            format="static",
            file_type="png",
            size={"width": 1080, "height": 1080},
        ),
        generate_image=True,
        reference_asset_ids=[request_asset_id],
    )

    content_version = await service.generate(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        payload=payload,
    )

    assert orchestrator.request is not None
    assert orchestrator.request.logo_asset_path == "tenant/brand/logo/jiraaf-horizontal-dark.png"
    assert len(orchestrator.request.logo_asset_candidates) == 2
    assert orchestrator.request.content_format_guide["summary"] == "Instagram static should stay decisive and scan-friendly."
    assert orchestrator.request.session_memory["follow_up_intent"]["mode"] == "variant_of_previous"
    assert orchestrator.request.session_memory["latest_content_version"]["scene_graph"]["styles"]["layout_archetype"] == "editorial_stack"
    assert len(orchestrator.request.asset_catalog) == 2
    assert content_version.explainability_metadata["render_authority"] == "ai"
    assert content_version.explainability_metadata["final_render_asset"]["storage_path"] == "tenant/brand/generated/final-render.png"
    assert any(isinstance(item, GeneratedAsset) and item.asset_role == AssetRole.RENDER_PREVIEW for item in saved_assets.items)


@pytest.mark.asyncio
async def test_content_generate_honors_explicit_new_content_request_mode_over_session_memory() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    user_id = uuid4()
    prior_content_id = uuid4()
    request_asset_id = uuid4()
    session = SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversational_context={"message_count": 2},
    )
    brand = SimpleNamespace(
        id=brand_space_id,
        tenant_id=tenant_id,
        lifecycle_state=BrandSpaceLifecycle.ACTIVE,
        resolved_brand_context={"identity": {}, "visual_identity": {}},
    )
    persona = SimpleNamespace(
        id=uuid4(),
        is_default=True,
        name="Working Professional",
        role="Investor",
        psychographics={},
        demographics={},
        audience_goals=[],
        motivations=[],
        fears_and_pain_points=[],
        objections=[],
        content_behavior={},
        language_preference="English",
    )
    objective = SimpleNamespace(
        id=uuid4(),
        is_default=True,
        name="Education",
        description="Make policy shifts relevant for investors.",
        content_type="content",
        platform_scope=["instagram"],
        configuration={},
    )
    response = AIOrchestrationResponse(
        text=StructuredTextPayload(headline="Fresh Census angle", body="Body", cta="Explore", hashtags=[], metadata={}),
        blueprint=BlueprintPayload(
            layout_type="single-panel",
            zones=[],
            hierarchy=["headline", "cta"],
            text_blocks=[],
            image_zones=[],
            logo_rules={},
            cta_placement={},
            platform_preset="instagram",
            export_format="png",
            overflow_strategy={"mode": "shrink_then_wrap"},
        ),
        creative_decision=CreativeDecisionPayload(layout_mode="synthesized_layout"),
        scene_graph=GenerationSceneGraph.model_validate(
            {
                "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                "elements": [],
                "styles": {},
            }
        ),
        validation_report=SceneGraphValidationReport(status="ok", issues=[]),
        message_strategy=MessageStrategyPayload(),
        explainability={},
        image_assets=[],
        final_render_asset=GeneratedImageAsset(
            asset_id=uuid4(),
            mime_type="image/png",
            storage_path="tenant/brand/generated/final-render.png",
            width=1080,
            height=1080,
            asset_role="render_preview",
            metadata={"slide_index": 1, "slide_count": 1},
        ),
        final_render_assets=[],
        render_authority="ai",
        tone_analysis={"score": 0.91, "summary": "on-brand"},
    )
    orchestrator = _CaptureOrchestrator(response)
    saved_contents = _AsyncCollector()
    saved_assets = _AsyncCollector()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    service.orchestrator = orchestrator
    service.contents = saved_contents
    service.assets = saved_assets
    service.content_format_guide = SimpleNamespace(load=lambda: {})
    service.trace = SimpleNamespace(start_trace=lambda **kwargs: {"trace_id": "trace-new"}, write_payload=lambda *args, **kwargs: None)

    async def _refresh_brand_context(_brand_space_id):
        return brand, {}

    async def _gather_context(_brand_space_id):
        return {"brand": brand, "sections": [], "personas": [persona], "objectives": [objective]}

    async def _get_or_create_session(*args, **kwargs):
        return session

    async def _build_session_memory(**kwargs):
        return {
            "follow_up_intent": {"mode": "variant_of_previous", "uses_previous_output": True},
            "latest_content_version": {
                "id": str(prior_content_id),
                "headline": "Old India-NZ FTA headline",
                "scene_graph": {"styles": {"layout_archetype": "editorial_stack"}},
            },
            "inherited_persona_id": str(uuid4()),
            "inherited_objective_id": str(uuid4()),
            "inherited_template_id": str(uuid4()),
        }

    async def _resolve_request_reference_assets(*args, **kwargs):
        return [
            {
                "asset_id": str(request_asset_id),
                "asset_role": "reference_creative",
                "storage_path": "tenant/brand/reference/request-census.png",
                "mime_type": "image/png",
                "trust_level": "trusted",
            }
        ]

    async def _resolve_brand_reference_assets(*args, **kwargs):
        return []

    async def _resolve_generation_decision(**kwargs):
        return {"mode": "synthesized_layout", "asset_strategy": {"dominant_visual_system": "generated_image"}}

    async def _collect_logo_asset_candidates(*args, **kwargs):
        return []

    async def _resolve_logo_asset_selection(*args, **kwargs):
        return None

    async def _build_retrieved_knowledge(*args, **kwargs):
        return {}, {}

    async def _record_session_context(*args, **kwargs):
        return None

    async def _recommend(**kwargs):
        return []

    async def _get_template(*args, **kwargs):
        return None

    async def _get_template_meta(*args, **kwargs):
        return None

    async def _enforce(*args, **kwargs):
        return None

    async def _increment(*args, **kwargs):
        return None

    service.validator = SimpleNamespace(refresh_brand_context=_refresh_brand_context)
    service._gather_context = _gather_context
    service._get_or_create_session = _get_or_create_session
    service._build_session_memory = _build_session_memory
    service._resolve_request_reference_assets = _resolve_request_reference_assets
    service._resolve_brand_reference_assets = _resolve_brand_reference_assets
    service._resolve_generation_decision = _resolve_generation_decision
    service._collect_logo_asset_candidates = _collect_logo_asset_candidates
    service._resolve_logo_asset_selection = _resolve_logo_asset_selection
    service._build_retrieved_knowledge = _build_retrieved_knowledge
    service._record_session_context = _record_session_context
    service.template_service = SimpleNamespace(recommend=_recommend)
    service.templates = SimpleNamespace(get_scoped=_get_template)
    service.template_metadata = SimpleNamespace(get_by_template=_get_template_meta)
    service.usage = SimpleNamespace(enforce=_enforce, increment=_increment)

    payload = ContentGenerateRequest(
        prompt="Create a LinkedIn carousel for Jiraaf on how Census 2027 could impact India's financial future.",
        request_mode="new_content",
        inheritance_policy=RequestInheritancePolicy(
            inherit_persona=False,
            inherit_objective=False,
            inherit_template=False,
            inherit_reference_assets=False,
            inherit_copy_context=False,
            inherit_layout_context=False,
        ),
        studio_panel=StudioPanelSelection(
            platform_preset="instagram",
            format="static",
            file_type="png",
            size={"width": 1080, "height": 1080},
        ),
        generate_image=True,
        reference_asset_ids=[request_asset_id],
    )

    content_version = await service.generate(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        payload=payload,
    )

    assert orchestrator.request is not None
    assert orchestrator.request.session_memory["follow_up_intent"]["mode"] == "new_content"
    assert orchestrator.request.session_memory["follow_up_intent"]["uses_previous_output"] is False
    assert content_version.parent_version_id is None


@pytest.mark.asyncio
async def test_content_export_refuses_backend_render_when_ai_asset_is_missing_for_single_image_png() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    content_version_id = uuid4()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    service.trace = SimpleNamespace(write_payload=lambda *args, **kwargs: None)

    content = SimpleNamespace(
        id=content_version_id,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        parent_version_id=None,
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        explainability_metadata={
            "render_authority": "ai",
            "generation_trace_id": "trace-1",
            "creative_decision": {"layout_mode": "synthesized_layout"},
            "scene_graph": {"canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"}, "elements": [], "styles": {}},
        },
        generated_payload={"headline": "Book Flights Smarter", "body": "Save more on every trip.", "cta": "Explore more", "hashtags": [], "metadata": {}},
        blueprint_payload={},
        selected_template_id=None,
    )
    brand = SimpleNamespace(name="Jiraaf", resolved_brand_context={"identity": {}, "visual_identity": {}})

    async def _get_content_scoped(*args, **kwargs):
        return content

    async def _get_brand_scoped(*args, **kwargs):
        return brand

    async def _list_assets(*args, **kwargs):
        return []

    async def _get_template(*args, **kwargs):
        return None

    async def _get_template_meta(*args, **kwargs):
        return None

    async def _resolve_logo(*args, **kwargs):
        return None

    service._get_content_scoped = _get_content_scoped
    service.brands = SimpleNamespace(get_scoped=_get_brand_scoped)
    service.assets = SimpleNamespace(list_by_content=_list_assets)
    service.templates = SimpleNamespace(get_scoped=_get_template)
    service.template_metadata = SimpleNamespace(get_by_template=_get_template_meta)
    service._resolve_logo_asset_path = _resolve_logo

    with pytest.raises(GenerationFailureError, match="AI final render asset is missing"):
        await service.export(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=content_version_id,
            studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        )


@pytest.mark.asyncio
async def test_content_export_regenerates_ai_assets_for_rewrite_carousel_without_backend_renderer() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    content_version_id = uuid4()
    parent_version_id = uuid4()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    service.trace = SimpleNamespace(write_payload=lambda *args, **kwargs: None)
    service.renderer = SimpleNamespace(render=None)

    content = SimpleNamespace(
        id=content_version_id,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        session_id=uuid4(),
        created_by=uuid4(),
        parent_version_id=parent_version_id,
        selected_template_id=None,
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1350}},
        explainability_metadata={
            "render_authority": "ai",
            "generation_trace_id": "trace-2",
            "creative_decision": {"layout_mode": "synthesized_layout"},
            "scene_graph": {"canvas": {"width": 1080, "height": 1350, "platform": "linkedin", "file_type": "png"}, "elements": [], "styles": {}},
            "selected_reference_images": [],
            "conditioning_reference_images": [],
            "message_strategy": {},
            "validation_report": {},
            "selective_regeneration_plan": {
                "targeted_slide_indexes": [1, 2, 3, 4, 5],
                "rewrite_source_content_version_id": str(parent_version_id),
                "only_targeted": True,
            },
        },
        generated_payload={"headline": "Hook", "body": "Body", "cta": "", "hashtags": [], "metadata": {}},
        blueprint_payload={},
    )
    brand = SimpleNamespace(name="Jiraaf", resolved_brand_context={"identity": {}, "visual_identity": {}})

    async def _get_content_scoped(_tenant_id, _brand_space_id, candidate_id):
        if candidate_id == content_version_id:
            return content
        raise NotFoundError("missing")

    async def _get_brand_scoped(*args, **kwargs):
        return brand

    async def _list_assets(*args, **kwargs):
        return []

    async def _get_template(*args, **kwargs):
        return None

    async def _get_template_meta(*args, **kwargs):
        return None

    async def _resolve_logo(*args, **kwargs):
        return None

    async def _collect_logo_candidates(*args, **kwargs):
        return []

    async def _resolve_logo_selection(*args, **kwargs):
        return {}

    regenerated_assets = [
        GeneratedAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=content_version_id,
            asset_role=AssetRole.RENDER_PREVIEW,
            mime_type="image/png",
            storage_path="tenant/brand/generated/final-render-slide-1.png",
            width=1080,
            height=1350,
            metadata_json={"render_source": "ai", "generation_stage": "final_render", "slide_index": 1, "slide_count": 2},
        ),
        GeneratedAsset(
            id=uuid4(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=content_version_id,
            asset_role=AssetRole.RENDER_EXPORT,
            mime_type="image/png",
            storage_path="tenant/brand/generated/final-render-slide-2.png",
            width=1080,
            height=1350,
            metadata_json={"render_source": "ai", "generation_stage": "final_render", "slide_index": 2, "slide_count": 2},
        ),
    ]

    calls = {"regenerated": 0}

    async def _regenerate(*args, **kwargs):
        calls["regenerated"] += 1
        return regenerated_assets

    service._get_content_scoped = _get_content_scoped
    service.brands = SimpleNamespace(get_scoped=_get_brand_scoped)
    service.assets = SimpleNamespace(list_by_content=_list_assets)
    service.templates = SimpleNamespace(get_scoped=_get_template)
    service.template_metadata = SimpleNamespace(get_by_template=_get_template_meta)
    service._resolve_logo_asset_path = _resolve_logo
    service._collect_logo_asset_candidates = _collect_logo_candidates
    service._resolve_logo_asset_selection = _resolve_logo_selection
    service._regenerate_ai_final_render_assets_for_rewrite = _regenerate

    payload = await service.export(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        content_version_id=content_version_id,
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1350}},
    )

    assert calls["regenerated"] == 1
    assert payload["renderer_metadata"]["render_authority"] == "ai"
    assert len(payload["export_assets"]) == 2


@pytest.mark.asyncio
async def test_content_rewrite_builds_strategy_and_qa_aware_prompt() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    user_id = uuid4()
    original_id = uuid4()
    session_id = uuid4()
    persona_id = uuid4()
    objective_id = uuid4()
    template_id = uuid4()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    brand = SimpleNamespace(
        id=brand_space_id,
        tenant_id=tenant_id,
        lifecycle_state=BrandSpaceLifecycle.ACTIVE,
        resolved_brand_context={
            "brand_name": "LedgerFlow",
            "voice_tone": {"tone_attributes": ["Confident"]},
            "guardrails": {"blocked_words": []},
        },
    )
    original = SimpleNamespace(
        id=original_id,
        session_id=session_id,
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png", "size": {"width": 1200, "height": 628}},
        selected_persona_id=persona_id,
        objective_id=objective_id,
        selected_template_id=template_id,
        prompt="Create a LinkedIn ad for finance leaders who need faster monthly close reporting.",
        generated_payload={
            "headline": "Close the Books Without Chasing Spreadsheets",
            "body": "See where finance work slows down and move the monthly close faster.",
            "cta": "Book a demo",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "hook_type": "problem-solution",
                "proof_points": ["Finance teams report 6 hours saved weekly", "Implementation in 2 weeks"],
                "trust_builders": ["SOC 2 ready", "Used by multi-entity finance teams"],
                "objection_handling": ["Worried about switching costs? onboarding is guided end-to-end."],
                "claim_evidence_pairs": [
                    {
                        "claim": "Reduce reporting prep time",
                        "evidence": "Teams save 6 hours a week on recurring reporting tasks",
                    }
                ],
            },
        },
        explainability_metadata={
            "message_strategy": {
                "primary_campaign_theme": "Finance leaders need faster close visibility without more manual work",
                "narrative_arc": ["pain", "proof", "cta"],
            },
            "validation_report": {"status": "clean", "notes": ["proof present"]},
            "compiled_context": {
                "brand_copy_brief": {"brand_name": "LedgerFlow", "brand_foundations": "Faster close visibility with operational confidence."},
                "audience_brief": {"objections": ["Switching finance systems feels risky"]},
                "objective_brief": {"name": "Demo generation"},
                "template_fit_brief": {"mode": "adapted_template", "template_name": "Finance hero layout"},
                "render_constraints": {"max_headline_chars": 80},
                "session_brief": {"follow_up_mode": "modify_previous"},
                "prompt_intelligence_brief": {"platform_rules": ["Lead with concrete proof for LinkedIn buyers."]},
                "knowledge_brief": ["Finance teams save hours when recurring reporting is automated."],
            },
        },
        tone_score=71,
        tone_feedback={
            "score": 71,
            "matched_signals": ["Confident and direct tone"],
            "deviations": ["Proof could be sharper"],
            "rewrite_suggestions": ["Make the evidence more concrete."],
            "quality_summary": ["Proof is too thin relative to the claims being made."],
            "persuasion_dimensions": {
                "brand_alignment": 78,
                "proof_strength": 58,
                "objection_handling": 64,
                "distinctiveness": 66,
                "clarity": 74,
                "cta_strength": 61,
            },
            "field_guidance": {
                "headline": ["Make the headline carry a clearer persuasion angle."],
                "body": ["Tie the body's main claim to concrete proof."],
                "cta": ["Replace generic CTA language with a concrete next step."],
                "metadata": ["Strengthen claim_evidence_pairs with concrete evidence."],
            },
        },
    )
    provider = _CaptureTextProvider(
        {
            "headline": "Close Faster Without More Headcount",
            "body": "See where finance work slows down and fix it before month-end.",
            "cta": "See the workflow",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "proof_points": [],
                "trust_builders": [],
                "objection_handling": [],
                "claim_evidence_pairs": [],
                "hook_type": "",
            },
        }
    )

    async def _get_content_scoped(*args, **kwargs):
        return original

    async def _get_brand(_brand_space_id):
        return brand

    async def _list_personas(*args, **kwargs):
        return []

    async def _list_objectives(*args, **kwargs):
        return []

    async def _refresh(*args, **kwargs):
        return None

    async def _noop(*args, **kwargs):
        return None

    async def _should_not_generate(*args, **kwargs):
        raise AssertionError("rewrite should not call the full generate() path")

    service._get_content_scoped = _get_content_scoped
    service.generate = _should_not_generate
    service.brands = SimpleNamespace(get=_get_brand)
    service.personas = SimpleNamespace(list_by_brand=_list_personas)
    service.objectives = SimpleNamespace(list_by_brand=_list_objectives)
    service.usage = SimpleNamespace(enforce=_noop, increment=_noop)
    service.orchestrator.providers = SimpleNamespace(get_text_provider=lambda *_args, **_kwargs: provider)
    service._refresh_content_tone_feedback = _refresh

    rewritten = await service.rewrite(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        payload=ContentRewriteRequest(
            content_version_id=original_id,
            rewrite_instruction="Make it sharper for skeptical finance buyers and keep the same offer.",
            studio_panel=StudioPanelSelection(
                platform_preset="linkedin",
                format="static",
                file_type="png",
                size={"width": 1200, "height": 628},
            ),
        ),
    )

    assert provider.envelope is not None
    assert provider.fallback["headline"] == ""
    assert provider.fallback["body"] == ""
    assert provider.fallback["cta"] == ""
    assert "This is a rewrite of existing structured content, not a fresh campaign brief." in provider.envelope.system
    assert "Current structured content:" in provider.envelope.user
    assert "Current message strategy:" in provider.envelope.user
    assert "Current tone QA:" in provider.envelope.user
    assert "Field rewrite plan:" in provider.envelope.user
    assert "Compiled rewrite context:" in provider.envelope.user
    assert '"hook_type": "problem-solution"' in provider.envelope.user
    assert '"claim_evidence_pairs"' in provider.envelope.user
    assert '"must_preserve"' in provider.envelope.user
    assert '"priority_fixes"' in provider.envelope.user
    assert "Rewrite only the targeted fields that actually need changes" in provider.envelope.system
    assert rewritten.parent_version_id == original_id
    assert rewritten.lifecycle_state == ContentLifecycle.EDITED
    assert rewritten.prompt == "Make it sharper for skeptical finance buyers and keep the same offer."


@pytest.mark.asyncio
async def test_content_rewrite_repairs_persuasion_metadata_and_refreshes_tone_feedback() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    user_id = uuid4()
    original_id = uuid4()
    session_id = uuid4()
    persona_id = uuid4()
    objective_id = uuid4()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    original = SimpleNamespace(
        id=original_id,
        session_id=session_id,
        selected_persona_id=persona_id,
        objective_id=objective_id,
        selected_template_id=None,
        prompt="Create a LinkedIn ad for finance leaders who need faster monthly close reporting.",
        generated_payload={
            "headline": "Close the Books Without Chasing Spreadsheets",
            "body": "See where finance work slows down and move the monthly close faster.",
            "cta": "Book a demo",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "hook_type": "problem-solution",
                "proof_points": ["Finance teams save 6 hours weekly on recurring reporting"],
                "trust_builders": ["SOC 2 ready", "Used by multi-entity finance teams"],
                "objection_handling": ["Switching feels risky, so onboarding is guided end-to-end."],
                "claim_evidence_pairs": [
                    {
                        "claim": "Reduce reporting prep time",
                        "evidence": "Finance teams save 6 hours weekly on recurring reporting",
                    }
                ],
            },
        },
        explainability_metadata={
            "message_strategy": {
                "primary_campaign_theme": "Faster close visibility with less manual work",
                "important_keywords": ["finance", "close", "reporting"],
            },
            "scene_graph": {
                "elements": [
                    {"element_id": "headline", "role": "headline", "text": "Old headline"},
                    {"element_id": "body", "role": "body", "text": "Old body"},
                    {"element_id": "supporting_line", "role": "supporting_line", "text": "Old support"},
                    {"element_id": "proof_points", "role": "proof_points", "text": ["Old proof"]},
                    {"element_id": "cta", "role": "cta", "text": "Old CTA"},
                ]
            },
        },
        tone_score=68,
        tone_feedback={
            "score": 68,
            "persuasion_dimensions": {
                "brand_alignment": 74,
                "proof_strength": 52,
                "objection_handling": 55,
                "distinctiveness": 66,
                "clarity": 73,
                "cta_strength": 61,
            },
            "field_guidance": {
                "body": ["Tie the main claim to concrete proof."],
                "cta": ["Replace the CTA with a more concrete next step."],
            },
        },
    )
    rewritten_result = SimpleNamespace(
        id=uuid4(),
        session_id=session_id,
        selected_persona_id=persona_id,
        objective_id=objective_id,
        selected_template_id=None,
        generated_payload={
            "headline": "Close Faster Without More Headcount",
            "body": "See where finance work slows down and fix it before month-end.",
            "cta": "See the workflow",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "supporting_line": "See where finance work slows down",
                "proof_points": [],
                "trust_builders": [],
                "objection_handling": [],
                "claim_evidence_pairs": [],
                "hook_type": "",
            },
        },
        explainability_metadata={
            "message_strategy": {
                "primary_campaign_theme": "Faster close visibility with less manual work",
                "important_keywords": ["finance", "close", "reporting"],
            },
            "scene_graph": {
                "elements": [
                    {"element_id": "headline", "role": "headline", "text": "Old headline"},
                    {"element_id": "body", "role": "body", "text": "Old body"},
                    {"element_id": "supporting_line", "role": "supporting_line", "text": "Old support"},
                    {"element_id": "proof_points", "role": "proof_points", "text": ["Old proof"]},
                    {"element_id": "cta", "role": "cta", "text": "Old CTA"},
                ]
            },
        },
        tone_score=51,
        tone_feedback={"score": 51},
        parent_version_id=None,
        lifecycle_state=ContentLifecycle.GENERATED,
        title="Close Faster Without More Headcount",
    )
    brand = SimpleNamespace(
        id=brand_space_id,
        tenant_id=tenant_id,
        resolved_brand_context={"voice_tone": {"tone_attributes": ["Confident"]}, "guardrails": {"blocked_words": []}},
    )
    persona = SimpleNamespace(
        id=persona_id,
        name="Finance leader",
        role="buyer",
        psychographics={},
        demographics={},
        audience_goals=["Reduce close time"],
        motivations=["Move faster without adding headcount"],
        fears_and_pain_points=["Manual reporting delays"],
        objections=["Switching tools feels risky"],
        content_behavior={},
        language_preference="en",
    )
    objective = SimpleNamespace(
        id=objective_id,
        name="Demo generation",
        description="Drive finance demo requests",
        content_type="social",
        platform_scope=["linkedin"],
        configuration={},
    )
    captured_tone: dict[str, object] = {}

    async def _get_content_scoped(*args, **kwargs):
        return original

    async def _get_brand(_brand_space_id):
        return brand

    async def _list_personas(*args, **kwargs):
        return [persona]

    async def _list_objectives(*args, **kwargs):
        return [objective]

    def _evaluate(**kwargs):
        captured_tone.update(kwargs)
        return {
            "score": 86,
            "matched_signals": ["Claim/evidence pairs are present in structured metadata"],
            "deviations": [],
            "rewrite_suggestions": [],
            "quality_summary": ["Copy is reasonably aligned, differentiated, and specific for the current brand constraints."],
            "persuasion_dimensions": {
                "brand_alignment": 80,
                "proof_strength": 84,
                "objection_handling": 82,
                "distinctiveness": 76,
                "clarity": 78,
                "cta_strength": 74,
            },
            "field_guidance": {"headline": ["Keep the hook explicit."]},
        }

    async def _candidate_payload(*args, **kwargs):
        return rewritten_result.generated_payload

    async def _noop(*args, **kwargs):
        return None

    service._get_content_scoped = _get_content_scoped
    service._generate_rewrite_candidate_payload = _candidate_payload
    service.brands = SimpleNamespace(get=_get_brand)
    service.personas = SimpleNamespace(list_by_brand=_list_personas)
    service.objectives = SimpleNamespace(list_by_brand=_list_objectives)
    service.tone = SimpleNamespace(evaluate=_evaluate)
    service.usage = SimpleNamespace(enforce=_noop, increment=_noop)

    rewritten = await service.rewrite(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        payload=ContentRewriteRequest(
            content_version_id=original_id,
            rewrite_instruction="Tighten the headline and make the body sharper for skeptical finance buyers, but keep the same offer.",
            studio_panel=StudioPanelSelection(
                platform_preset="linkedin",
                format="static",
                file_type="png",
                size={"width": 1200, "height": 628},
            ),
        ),
    )

    metadata = rewritten.generated_payload["metadata"]
    assert metadata["hook_type"] == "problem-solution"
    assert metadata["proof_points"][0] == "Finance teams save 6 hours weekly on recurring reporting"
    assert metadata["trust_builders"][0] == "SOC 2 ready"
    assert metadata["objection_handling"][0].startswith("Switching feels risky")
    assert metadata["claim_evidence_pairs"][0]["claim"] == "Reduce reporting prep time"
    assert rewritten.explainability_metadata["rewrite_preservation"]["restored_fields"] == [
        "proof_points",
        "trust_builders",
        "objection_handling",
        "claim_evidence_pairs",
        "hook_type",
    ]
    assert rewritten.explainability_metadata["scene_graph"]["elements"][3]["text"][0] == (
        "Finance teams save 6 hours weekly on recurring reporting"
    )
    assert rewritten.tone_score == 86
    assert rewritten.tone_feedback["persuasion_dimensions"]["proof_strength"] == 84
    assert captured_tone["content_payload"]["metadata"]["claim_evidence_pairs"][0]["claim"] == "Reduce reporting prep time"
    assert captured_tone["persona_context"]["name"] == "Finance leader"
    assert rewritten.parent_version_id == original_id
    assert rewritten.lifecycle_state == ContentLifecycle.EDITED


@pytest.mark.asyncio
async def test_content_rewrite_respects_explicit_metadata_replacement_in_instruction() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    user_id = uuid4()
    original_id = uuid4()
    session_id = uuid4()
    persona_id = uuid4()
    objective_id = uuid4()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    original = SimpleNamespace(
        id=original_id,
        session_id=session_id,
        selected_persona_id=persona_id,
        objective_id=objective_id,
        selected_template_id=None,
        prompt="Create a LinkedIn ad for finance leaders who need faster monthly close reporting.",
        generated_payload={
            "headline": "Close the Books Without Chasing Spreadsheets",
            "body": "See where finance work slows down and move the monthly close faster.",
            "cta": "Book a demo",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "trust_builders": ["SOC 2 ready"],
                "proof_points": ["Finance teams save 6 hours weekly on recurring reporting"],
            },
        },
        explainability_metadata={"message_strategy": {}},
        tone_score=68,
        tone_feedback={"score": 68},
    )
    rewritten_result = SimpleNamespace(
        id=uuid4(),
        session_id=session_id,
        selected_persona_id=persona_id,
        objective_id=objective_id,
        selected_template_id=None,
        generated_payload={
            "headline": "Close Faster With Enterprise-Ready Controls",
            "body": "Move faster without losing operational confidence.",
            "cta": "See the workflow",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "trust_builders": ["ISO 27001 certified"],
                "proof_points": [],
            },
        },
        explainability_metadata={"message_strategy": {}},
        tone_score=50,
        tone_feedback={"score": 50},
        parent_version_id=None,
        lifecycle_state=ContentLifecycle.GENERATED,
        title="Close Faster With Enterprise-Ready Controls",
    )
    brand = SimpleNamespace(
        id=brand_space_id,
        tenant_id=tenant_id,
        resolved_brand_context={"voice_tone": {"tone_attributes": ["Confident"]}, "guardrails": {"blocked_words": []}},
    )

    async def _get_content_scoped(*args, **kwargs):
        return original

    async def _get_brand(_brand_space_id):
        return brand

    async def _list_personas(*args, **kwargs):
        return []

    async def _list_objectives(*args, **kwargs):
        return []

    def _evaluate(**kwargs):
        return {
            "score": 79,
            "matched_signals": [],
            "deviations": [],
            "rewrite_suggestions": [],
            "quality_summary": [],
            "persuasion_dimensions": {"proof_strength": 72},
            "field_guidance": {},
        }

    async def _candidate_payload(*args, **kwargs):
        return rewritten_result.generated_payload

    async def _noop(*args, **kwargs):
        return None

    service._get_content_scoped = _get_content_scoped
    service._generate_rewrite_candidate_payload = _candidate_payload
    service.brands = SimpleNamespace(get=_get_brand)
    service.personas = SimpleNamespace(list_by_brand=_list_personas)
    service.objectives = SimpleNamespace(list_by_brand=_list_objectives)
    service.tone = SimpleNamespace(evaluate=_evaluate)
    service.usage = SimpleNamespace(enforce=_noop, increment=_noop)

    rewritten = await service.rewrite(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        payload=ContentRewriteRequest(
            content_version_id=original_id,
            rewrite_instruction="Replace SOC 2 ready with ISO 27001 certified trust language and keep the rest tighter.",
            studio_panel=StudioPanelSelection(
                platform_preset="linkedin",
                format="static",
                file_type="png",
                size={"width": 1200, "height": 628},
            ),
        ),
    )

    assert rewritten.generated_payload["metadata"]["trust_builders"] == ["ISO 27001 certified"]
    assert "SOC 2 ready" not in rewritten.generated_payload["metadata"]["trust_builders"]


@pytest.mark.asyncio
async def test_content_rewrite_rejects_incomplete_rewrite_instead_of_backfilling_original_copy() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    user_id = uuid4()
    original_id = uuid4()

    session = _DummyAsyncSession()
    service = ContentService(session)  # type: ignore[arg-type]
    original = SimpleNamespace(
        id=original_id,
        session_id=uuid4(),
        selected_persona_id=uuid4(),
        objective_id=uuid4(),
        selected_template_id=None,
        prompt="Create a LinkedIn ad for finance leaders who need faster monthly close reporting.",
        generated_payload={
            "headline": "Close the Books Without Chasing Spreadsheets",
            "body": "See where finance work slows down and move the monthly close faster.",
            "cta": "Book a demo",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "proof_points": ["Finance teams save 6 hours weekly on recurring reporting"],
            },
        },
        explainability_metadata={"message_strategy": {}},
        tone_score=68,
        tone_feedback={"score": 68},
    )
    rewritten_result = SimpleNamespace(
        generated_payload={
            "headline": "",
            "body": "",
            "cta": "",
            "hashtags": [],
            "metadata": {},
        },
    )

    async def _get_content_scoped(*args, **kwargs):
        return original

    brand = SimpleNamespace(
        id=brand_space_id,
        tenant_id=tenant_id,
        lifecycle_state=BrandSpaceLifecycle.ACTIVE,
        resolved_brand_context={"voice_tone": {"tone_attributes": ["Confident"]}, "guardrails": {"blocked_words": []}},
    )

    async def _get_brand(_brand_space_id):
        return brand

    usage_increments: list[tuple[object, object, object]] = []

    async def _increment(*args, **kwargs):
        usage_increments.append(
            (
                kwargs.get("tenant_id", args[0] if len(args) > 0 else None),
                kwargs.get("metric_code", args[1] if len(args) > 1 else None),
                kwargs.get("amount", args[2] if len(args) > 2 else 1),
            )
        )

    async def _candidate_payload(*args, **kwargs):
        return rewritten_result.generated_payload

    async def _noop(*args, **kwargs):
        return None

    async def _empty_list(*args, **kwargs):
        return []

    service._get_content_scoped = _get_content_scoped
    service._generate_rewrite_candidate_payload = _candidate_payload
    service.brands = SimpleNamespace(get=_get_brand)
    service.personas = SimpleNamespace(list_by_brand=_empty_list)
    service.objectives = SimpleNamespace(list_by_brand=_empty_list)
    service.usage = SimpleNamespace(enforce=_noop, increment=_increment)

    with pytest.raises(GenerationFailureError, match="missing required structured fields"):
        await service.rewrite(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            user_id=user_id,
            payload=ContentRewriteRequest(
                content_version_id=original_id,
                rewrite_instruction="Rewrite it for skeptical finance buyers with a stronger proof-led angle.",
                studio_panel=StudioPanelSelection(
                    platform_preset="linkedin",
                    format="static",
                    file_type="png",
                    size={"width": 1200, "height": 628},
                ),
            ),
        )

    assert session.deleted == []
    assert usage_increments == []
    assert session.added == []


@pytest.mark.asyncio
async def test_content_rewrite_drops_stale_persuasion_metadata_when_angle_changes() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    user_id = uuid4()
    original_id = uuid4()
    session_id = uuid4()
    persona_id = uuid4()
    objective_id = uuid4()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    original = SimpleNamespace(
        id=original_id,
        session_id=session_id,
        selected_persona_id=persona_id,
        objective_id=objective_id,
        selected_template_id=None,
        prompt="Create a LinkedIn ad for finance leaders who need faster monthly close reporting.",
        generated_payload={
            "headline": "Close the Books Without Chasing Spreadsheets",
            "body": "See where finance work slows down and move the monthly close faster.",
            "cta": "Book a demo",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "hook_type": "problem-solution",
                "supporting_line": "See where finance work slows down before month-end.",
                "proof_points": ["Finance teams save 6 hours weekly on recurring reporting"],
                "trust_builders": ["SOC 2 ready"],
                "claim_evidence_pairs": [
                    {
                        "claim": "Reduce reporting prep time",
                        "evidence": "Finance teams save 6 hours weekly on recurring reporting",
                    }
                ],
            },
        },
        explainability_metadata={"message_strategy": {}},
        tone_score=68,
        tone_feedback={"score": 68},
    )
    rewritten_result = SimpleNamespace(
        id=uuid4(),
        session_id=session_id,
        selected_persona_id=persona_id,
        objective_id=objective_id,
        selected_template_id=None,
        generated_payload={
            "headline": "Enterprise Controls That Keep Finance Audit-Ready",
            "body": "Give compliance-conscious finance teams clearer approval guardrails and audit trails.",
            "cta": "Review the controls",
            "hashtags": ["#FinanceOps"],
            "metadata": {
                "proof_points": [],
                "trust_builders": [],
                "claim_evidence_pairs": [],
                "objection_handling": [],
                "hook_type": "",
            },
        },
        explainability_metadata={"message_strategy": {}},
        tone_score=52,
        tone_feedback={"score": 52},
        parent_version_id=None,
        lifecycle_state=ContentLifecycle.GENERATED,
        title="Enterprise Controls That Keep Finance Audit-Ready",
    )
    brand = SimpleNamespace(
        id=brand_space_id,
        tenant_id=tenant_id,
        resolved_brand_context={"voice_tone": {"tone_attributes": ["Confident"]}, "guardrails": {"blocked_words": []}},
    )

    async def _get_content_scoped(*args, **kwargs):
        return original

    async def _get_brand(_brand_space_id):
        return brand

    async def _list_personas(*args, **kwargs):
        return []

    async def _list_objectives(*args, **kwargs):
        return []

    def _evaluate(**kwargs):
        return {
            "score": 82,
            "matched_signals": [],
            "deviations": [],
            "rewrite_suggestions": [],
            "quality_summary": [],
            "persuasion_dimensions": {
                "brand_alignment": 78,
                "proof_strength": 74,
                "objection_handling": 71,
                "distinctiveness": 79,
                "clarity": 80,
                "cta_strength": 75,
            },
            "field_guidance": {},
        }

    async def _candidate_payload(*args, **kwargs):
        return rewritten_result.generated_payload

    async def _noop(*args, **kwargs):
        return None

    service._get_content_scoped = _get_content_scoped
    service._generate_rewrite_candidate_payload = _candidate_payload
    service.brands = SimpleNamespace(get=_get_brand)
    service.personas = SimpleNamespace(list_by_brand=_list_personas)
    service.objectives = SimpleNamespace(list_by_brand=_list_objectives)
    service.tone = SimpleNamespace(evaluate=_evaluate)
    service.usage = SimpleNamespace(enforce=_noop, increment=_noop)

    rewritten = await service.rewrite(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        payload=ContentRewriteRequest(
            content_version_id=original_id,
            rewrite_instruction="Reframe this around enterprise controls and risk reduction for compliance-conscious buyers.",
            studio_panel=StudioPanelSelection(
                platform_preset="linkedin",
                format="static",
                file_type="png",
                size={"width": 1200, "height": 628},
            ),
        ),
    )

    metadata = rewritten.generated_payload["metadata"]
    assert "Finance teams save 6 hours weekly on recurring reporting" not in metadata["proof_points"]
    assert metadata["trust_builders"] == []
    assert metadata["claim_evidence_pairs"] == []
    assert metadata["supporting_line"] != "See where finance work slows down before month-end."
    assert metadata["supporting_line"].rstrip(".") == (
        "Give compliance-conscious finance teams clearer approval guardrails and audit trails"
    )
    assert "proof_points" not in rewritten.explainability_metadata["rewrite_preservation"]["restored_fields"]
    assert "trust_builders" not in rewritten.explainability_metadata["rewrite_preservation"]["restored_fields"]
    assert "claim_evidence_pairs" not in rewritten.explainability_metadata["rewrite_preservation"]["restored_fields"]
    assert rewritten.explainability_metadata["rewrite_preservation"]["angle_shift_detected"] is True
    assert "proof_points" in rewritten.explainability_metadata["rewrite_preservation"]["stale_fields_dropped"]
    assert "trust_builders" in rewritten.explainability_metadata["rewrite_preservation"]["stale_fields_dropped"]
    assert "claim_evidence_pairs" in rewritten.explainability_metadata["rewrite_preservation"]["stale_fields_dropped"]


@pytest.mark.asyncio
async def test_content_tone_check_uses_stored_context_when_content_version_is_provided() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    content_version_id = uuid4()
    persona_id = uuid4()
    objective_id = uuid4()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    brand = SimpleNamespace(
        id=brand_space_id,
        tenant_id=tenant_id,
        resolved_brand_context={"voice_tone": {"tone_attributes": ["Confident"]}, "guardrails": {"blocked_words": []}},
    )
    content_version = SimpleNamespace(
        id=content_version_id,
        selected_persona_id=persona_id,
        objective_id=objective_id,
        generated_payload={
            "headline": "Close the books faster",
            "body": "Guided onboarding helps finance teams move without disruption.",
            "cta": "Book a demo",
            "metadata": {
                "hook_type": "problem-led",
                "proof_points": ["Finance teams save 6 hours a week on recurring reporting"],
                "objection_handling": ["Switching feels risky, so onboarding is guided end-to-end."],
                "claim_evidence_pairs": [
                    {
                        "claim": "Reduce close prep time",
                        "evidence": "Finance teams save 6 hours a week on recurring reporting",
                    }
                ],
            },
        },
        explainability_metadata={
            "message_strategy": {
                "primary_campaign_theme": "Faster close visibility with less manual work",
                "important_keywords": ["finance", "close", "reporting"],
            }
        },
    )
    persona = SimpleNamespace(
        id=persona_id,
        name="Finance leader",
        role="buyer",
        psychographics={},
        demographics={},
        audience_goals=["Reduce close time"],
        motivations=["Move faster"],
        fears_and_pain_points=["Manual reporting delays"],
        objections=["Switching tools feels risky"],
        content_behavior={},
        language_preference="en",
    )
    objective = SimpleNamespace(
        id=objective_id,
        name="Demo generation",
        description="Drive finance demo requests",
        content_type="social",
        platform_scope=["linkedin"],
        configuration={},
    )
    captured: dict[str, object] = {}

    async def _get_brand(_brand_space_id):
        return brand

    async def _get_content_scoped(*args, **kwargs):
        return content_version

    async def _list_personas(*args, **kwargs):
        return [persona]

    async def _list_objectives(*args, **kwargs):
        return [objective]

    def _evaluate(**kwargs):
        captured.update(kwargs)
        return {
            "score": 83,
            "matched_signals": ["Structured proof detected"],
            "deviations": [],
            "rewrite_suggestions": [],
            "quality_summary": [],
            "persuasion_dimensions": {"proof_strength": 81},
            "field_guidance": {"body": ["Keep proof tied to the audience outcome."]},
        }

    service.brands = SimpleNamespace(get=_get_brand)
    service._get_content_scoped = _get_content_scoped
    service.personas = SimpleNamespace(list_by_brand=_list_personas)
    service.objectives = SimpleNamespace(list_by_brand=_list_objectives)
    service.tone = SimpleNamespace(evaluate=_evaluate)

    result = await service.tone_check(
        brand_space_id,
        ToneCheckRequest(content_version_id=content_version_id),
    )

    assert result["score"] == 83
    assert captured["content"] == "Close the books faster. Guided onboarding helps finance teams move without disruption. Book a demo"
    assert captured["content_payload"]["metadata"]["claim_evidence_pairs"][0]["claim"] == "Reduce close prep time"
    assert captured["message_strategy"]["primary_campaign_theme"] == "Faster close visibility with less manual work"
    assert captured["persona_context"]["name"] == "Finance leader"
    assert captured["objective_context"]["name"] == "Demo generation"
