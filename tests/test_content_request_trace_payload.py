import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest

knowledge_stub = types.ModuleType("app.services.knowledge")


class _StubKnowledgeService:
    def __init__(self, _session) -> None:
        self.retrieval = SimpleNamespace(search=lambda *args, **kwargs: [])

    async def list(self, *_args, **_kwargs):
        return []


knowledge_stub.KnowledgeService = _StubKnowledgeService
sys.modules.setdefault("app.services.knowledge", knowledge_stub)

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
from app.core.enums import AssetRole, BrandSpaceLifecycle
from app.models.content import GeneratedAsset
from app.schemas.common import StudioPanelSelection
from app.schemas.content import ContentGenerateRequest, RequestInheritancePolicy
from app.services.content import ContentService


class _DummyAsyncSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.added = []

    async def commit(self) -> None:
        self.commit_count += 1
        return None

    async def flush(self) -> None:
        return None

    async def refresh(self, _item) -> None:
        return None

    def add(self, item) -> None:
        self.added.append(item)

    async def execute(self, *_args, **_kwargs):
        return _DummyResult()


class _DummyResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None


class _CaptureTrace:
    def __init__(self) -> None:
        self.payloads: dict[str, object] = {}
        self.debug_events: list[tuple[str, dict[str, object]]] = []
        self.brand_usage_reports: list[dict[str, object]] = []

    def start_trace(self, **_kwargs):  # noqa: ANN003, ANN201
        return {"trace_id": "trace-capture", "trace_dir": "storage/generation_traces/test-traces/trace-capture"}

    def write_payload(self, _trace_id, filename, payload):  # noqa: ANN001, ANN201
        self.payloads[str(filename)] = payload
        return filename

    def write_debug_event(self, event_type, payload):  # noqa: ANN001, ANN201
        self.debug_events.append((str(event_type), dict(payload or {})))
        return None

    def build_brand_usage_report(self, **kwargs):  # noqa: ANN003, ANN201
        report = {
            "trace_id": kwargs.get("trace_id"),
            "prompt": kwargs.get("prompt"),
            "selected_template": kwargs.get("selected_template"),
            "explainability": kwargs.get("explainability"),
        }
        return report

    def write_brand_usage_report(self, _trace_id, report):  # noqa: ANN001, ANN201
        copied = dict(report or {})
        self.brand_usage_reports.append(copied)
        self.payloads["brand_usage_report"] = copied
        return "brand_usage_report"


class _CaptureOrchestrator:
    def __init__(self, response: AIOrchestrationResponse) -> None:
        self.request = None
        self.response = response

    def generate(self, request):  # noqa: ANN001, ANN201
        self.request = request
        return self.response


class _FailingOrchestrator:
    def generate(self, request):  # noqa: ANN001, ANN201
        raise RuntimeError("forced orchestrator failure")


class _AsyncCollector:
    def __init__(self) -> None:
        self.items = []

    async def add(self, item) -> None:
        self.items.append(item)


def _orchestration_response() -> AIOrchestrationResponse:
    return AIOrchestrationResponse(
        text=StructuredTextPayload(headline="Fresh headline", body="Fresh body", cta="Explore", hashtags=[], metadata={}),
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


def _build_service_for_trace_capture(*, stale_prompt: str, stale_headline: str) -> tuple[ContentService, _CaptureTrace]:
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
        conversational_context={"message_count": 3, "last_response_mode": "visual_generation", "last_content_version_id": str(prior_content_id)},
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
        description="Make macro shifts relevant for investors.",
        content_type="content",
        platform_scope=["instagram"],
        configuration={},
    )

    orchestrator = _CaptureOrchestrator(_orchestration_response())
    saved_contents = _AsyncCollector()
    saved_assets = _AsyncCollector()
    trace = _CaptureTrace()

    service = ContentService(_DummyAsyncSession())  # type: ignore[arg-type]
    service.orchestrator = orchestrator
    service.contents = saved_contents
    service.assets = saved_assets
    service.content_format_guide = SimpleNamespace(load=lambda: {})
    service.trace = trace

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
                "prompt": stale_prompt,
                "headline": stale_headline,
                "scene_graph": {"styles": {"layout_archetype": "editorial_stack"}},
                "prompt_lineage": {"user_prompt_raw": stale_prompt},
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
                "storage_path": "tenant/brand/reference/request.png",
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

    async def _prepare_runtime_brand_context(*args, **kwargs):
        return brand.resolved_brand_context, [], None

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
    service._prepare_runtime_brand_context = _prepare_runtime_brand_context
    service.template_service = SimpleNamespace(recommend=_recommend)
    service.templates = SimpleNamespace(get_scoped=_get_template)
    service.template_metadata = SimpleNamespace(get_by_template=_get_template_meta)
    service.usage = SimpleNamespace(enforce=_enforce, increment=_increment)

    return service, trace


async def _capture_content_request(prompt: str) -> dict:
    stale_prompt = "Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement signed on 27 April 2026."
    stale_headline = "What's really inside the India-New Zealand Free Trade Deal?"
    service, trace = _build_service_for_trace_capture(stale_prompt=stale_prompt, stale_headline=stale_headline)

    payload = ContentGenerateRequest(
        prompt=prompt,
        raw_user_prompt=prompt,
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
        reference_asset_ids=[],
    )

    await service.generate(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        payload=payload,
    )

    return dict(trace.payloads["content_request"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt",
    [
        "Create a LinkedIn carousel post for Jiraaf on the topic: How Census 2027 could impact India's financial future.",
        "Write a LinkedIn carousel for Jiraaf on women borrowers reshaping credit access in India.",
    ],
)
async def test_content_request_trace_payload_keeps_fresh_user_prompt(prompt: str) -> None:
    payload = await _capture_content_request(prompt)

    assert payload["prompt"] == prompt
    assert payload["prompt_lineage"]["user_prompt_raw"] == prompt
    assert payload["prompt_lineage"]["generation_prompt_effective"] == prompt
    assert payload["request_lineage"]["request_mode"] == "new_content"
    assert payload["prompt_sanitization"]["effective_prompt_sanitized"] == prompt
    assert payload["prompt_sanitization"]["raw_user_prompt"] == prompt
    assert payload["prompt"] != "Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement signed on 27 April 2026."


@pytest.mark.asyncio
async def test_content_request_trace_payload_changes_for_different_prompts() -> None:
    census_prompt = "Create a LinkedIn carousel post for Jiraaf on the topic: How Census 2027 could impact India's financial future."
    women_prompt = "Write a LinkedIn carousel for Jiraaf on women borrowers reshaping credit access in India."

    census_payload = await _capture_content_request(census_prompt)
    women_payload = await _capture_content_request(women_prompt)

    assert census_payload["prompt"] == census_prompt
    assert women_payload["prompt"] == women_prompt
    assert census_payload["prompt"] != women_payload["prompt"]
    assert census_payload["prompt_lineage"]["user_prompt_raw"] != women_payload["prompt_lineage"]["user_prompt_raw"]


@pytest.mark.asyncio
async def test_content_generate_writes_brand_usage_snapshot_before_orchestrator_failure() -> None:
    prompt = "Create a LinkedIn infographic on women borrowers reshaping credit access in India."
    stale_prompt = "Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement signed on 27 April 2026."
    stale_headline = "What's really inside the India-New Zealand Free Trade Deal?"
    service, trace = _build_service_for_trace_capture(stale_prompt=stale_prompt, stale_headline=stale_headline)
    service.orchestrator = _FailingOrchestrator()

    payload = ContentGenerateRequest(
        prompt=prompt,
        raw_user_prompt=prompt,
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
            platform_preset="linkedin",
            format="infographic",
            file_type="png",
            size={"width": 1080, "height": 1350},
        ),
        generate_image=True,
        reference_asset_ids=[],
    )

    with pytest.raises(RuntimeError, match="forced orchestrator failure"):
        await service.generate(
            tenant_id=uuid4(),
            brand_space_id=uuid4(),
            user_id=uuid4(),
            payload=payload,
        )

    assert trace.brand_usage_reports
    assert trace.payloads["brand_usage_report"]["prompt"] == prompt
    assert trace.payloads["brand_usage_report"]["explainability"]["report_stage"] == "pre_orchestration"
