from uuid import uuid4
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.enums import AssetRole
from app.core.exceptions import GenerationFailureError, GuardrailViolationError
from app.integrations.object_storage import LocalObjectStorage
from app.models.content import ContentSession, ContentVersion, GeneratedAsset
from app.schemas.chat import ChatMessageCreateRequest
from app.schemas.common import StudioPanelSelection
from app.services.chat import ChatService
from app.services.intent_router import ChatIntentDecision
from app.services.text_content import TextGenerationResult


def test_chat_service_formats_assistant_text_from_generated_payload() -> None:
    text = ChatService.build_assistant_message_text(
        {
            "headline": "Launch Faster",
            "body": "Keep your brand voice consistent.",
            "cta": "Start now",
        }
    )
    assert "Launch Faster" in text
    assert "Start now" in text


def test_chat_service_builds_channel_citations() -> None:
    citations = ChatService.build_citations({"retrieval_channels": ["brand", "strategy"]})
    assert citations == [{"channel": "brand"}, {"channel": "strategy"}]


def test_chat_service_serializes_generated_assets() -> None:
    asset = GeneratedAsset(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        content_version_id=uuid4(),
        asset_role=AssetRole.RENDER_PREVIEW,
        mime_type="image/png",
        storage_path="tenant/brand/generated/preview.png",
        width=1200,
        height=627,
        metadata_json={},
    )
    payload = ChatService.serialize_asset(asset)
    assert payload["asset_role"] == "render_preview"
    assert payload["storage_path"].endswith("preview.png")
    assert payload["asset_url"]
    assert "token=" in payload["asset_url"]


def test_chat_service_makes_nested_uuid_payload_json_safe() -> None:
    payload = ChatService.make_json_safe(
        {
            "preview_asset": {
                "asset_id": uuid4(),
                "storage_path": "tenant/brand/generated/preview.png",
            },
            "export_assets": [{"asset_id": uuid4()}],
        }
    )
    assert isinstance(payload["preview_asset"]["asset_id"], str)
    assert isinstance(payload["export_assets"][0]["asset_id"], str)


def test_chat_service_decorates_structured_payload_assets_with_signed_urls(monkeypatch) -> None:
    temp_root = Path("C:/tmp") / f"violyt-chat-test-{uuid4()}"
    temp_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "app.integrations.object_storage.get_settings",
        lambda: SimpleNamespace(object_storage_base_path=str(temp_root)),
    )
    storage = LocalObjectStorage()
    stored_preview = storage.save_bytes(uuid4(), uuid4(), "generated", "preview.png", b"preview")
    stored_ai = storage.save_bytes(uuid4(), uuid4(), "generated", "ai.png", b"ai")
    payload = ChatService.decorate_structured_payload_assets(
        {
            "preview_asset": {
                "asset_id": str(uuid4()),
                "mime_type": "image/png",
                "storage_path": stored_preview.storage_path,
                "asset_role": "render_preview",
                "asset_url": "https://expired.example/preview",
            },
            "assets": [
                {
                    "asset_id": str(uuid4()),
                    "mime_type": "image/png",
                    "storage_path": stored_ai.storage_path,
                    "asset_role": "ai_image",
                    "asset_url": "https://expired.example/ai",
                }
            ],
        }
    )

    assert payload["preview_asset"]["asset_url"]
    assert payload["assets"][0]["asset_url"]
    assert payload["preview_asset"]["asset_url"] != "https://expired.example/preview"
    assert payload["assets"][0]["asset_url"] != "https://expired.example/ai"


def test_chat_service_filters_missing_structured_payload_assets() -> None:
    payload = ChatService.decorate_structured_payload_assets(
        {
            "preview_asset": {
                "asset_id": str(uuid4()),
                "mime_type": "image/png",
                "storage_path": "tenant/brand/generated/missing-preview.png",
                "asset_role": "render_preview",
                "asset_url": "https://expired.example/preview",
            },
            "assets": [
                {
                    "asset_id": str(uuid4()),
                    "mime_type": "image/png",
                    "storage_path": "tenant/brand/generated/missing-ai.png",
                    "asset_role": "ai_image",
                    "asset_url": "https://expired.example/ai",
                }
            ],
            "export_assets": [
                {
                    "asset_id": str(uuid4()),
                    "mime_type": "image/png",
                    "storage_path": "tenant/brand/generated/missing-export.png",
                    "asset_role": "render_export",
                    "asset_url": "https://expired.example/export",
                }
            ],
        }
    )

    assert payload["preview_asset"] is None
    assert payload["assets"] == []
    assert payload["export_assets"] == []


def test_chat_service_builds_retryable_generation_failure_payload() -> None:
    exc = GenerationFailureError(
        "AI final render failed and backend fallback rendering is disabled for this format.",
        failure_type="provider_failure",
        reason_code="ai_final_render_failed",
        user_safe_message="I couldn't generate the visual this time. Please regenerate.",
        retryable=True,
        rule_source="system",
        suggested_next_action="Regenerate the creative.",
        details={"stage": "final_render"},
    )

    message = ChatService.build_generation_failure_message_text(exc)
    payload = ChatService.build_generation_failure_payload(
        exc,
        generate_image=True,
        content_version_id=None,
    )

    assert message == "I couldn't generate the visual this time. Please regenerate."
    assert payload["generation_status"] == "failed"
    assert payload["failure"]["reason_code"] == "ai_final_render_failed"
    assert payload["can_regenerate"] is True


def test_chat_service_builds_guardrail_failure_payload_with_actual_reason() -> None:
    exc = GuardrailViolationError("Guaranteed-return claims are not allowed for this brand.")

    message = ChatService.build_generation_failure_message_text(exc)
    payload = ChatService.build_generation_failure_payload(
        exc,
        generate_image=True,
        content_version_id=None,
    )

    assert "Guaranteed-return claims are not allowed" in message
    assert payload["failure"]["failure_type"] == "guardrail_conflict"
    assert payload["failure"]["reason_summary"] == "Guaranteed-return claims are not allowed for this brand."
    assert payload["can_regenerate"] is False


@pytest.mark.asyncio
async def test_chat_service_routes_greeting_without_triggering_generation() -> None:
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={},
        is_active=True,
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(route=lambda message, context: ChatIntentDecision(mode="small_talk", reason="greeting"))
    chat.conversation = SimpleNamespace(
        reply=lambda **kwargs: {
            "message_text": "Hi! I'm ready to help.",
            "structured_payload": {"mode": "conversation", "conversation_mode": "small_talk"},
        }
    )
    chat.text_content = SimpleNamespace(generate=AsyncMock(), evaluate=AsyncMock())
    chat.content = SimpleNamespace(generate=AsyncMock(), export=AsyncMock())
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(message="Hi"),
    )

    assert assistant.message_text == "Hi! I'm ready to help."
    assert assistant.structured_payload["mode"] == "conversation"
    chat.content.generate.assert_not_awaited()
    chat.text_content.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_service_routes_text_only_requests_without_visual_generation() -> None:
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={},
        is_active=True,
    )
    content_version = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Write a LinkedIn post about bond duration.",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "Bond duration, explained", "body": "Body copy", "cta": "Read more"},
        blueprint_payload={},
        explainability_metadata={"retrieval_channels": ["knowledge"]},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(mode="content_only", deliverable_type="linkedin_post", reason="text_deliverable")
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(
        generate=AsyncMock(
            return_value=TextGenerationResult(
                content_version=content_version,
                assistant_payload={
                    "mode": "content_only",
                    "deliverable_type": "linkedin_post",
                    "generated_payload": content_version.generated_payload,
                    "artifact_state": {"planning_objects": {"deliverable_type": "linkedin_post"}},
                },
                assistant_text="Bond duration, explained\n\nBody copy\n\nRead more",
            )
        ),
        evaluate=AsyncMock(),
    )
    chat.content = SimpleNamespace(generate=AsyncMock(), export=AsyncMock())
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(message="Write a LinkedIn post about bond duration."),
    )

    assert assistant.content_version_id == content_version.id
    assert assistant.structured_payload["mode"] == "content_only"
    assert assistant.structured_payload["deliverable_type"] == "linkedin_post"
    assert session.conversational_context["artifact_state"]["planning_objects"]["deliverable_type"] == "linkedin_post"
    chat.content.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_service_routes_visual_requests_through_existing_generation_path() -> None:
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "pdf"},
        conversational_context={},
        is_active=True,
    )
    content_version = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Generate a LinkedIn carousel on bond mistakes.",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "Top Bond Mistakes", "body": "Slide content", "cta": "Explore Jiraaf"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(route=lambda message, context: ChatIntentDecision(mode="visual_generation", reason="visual_keywords"))
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(generate=AsyncMock(), evaluate=AsyncMock())
    chat.content = SimpleNamespace(
        generate=AsyncMock(return_value=content_version),
        export=AsyncMock(return_value={"export_assets": [], "renderer_metadata": {}, "preview_asset": None}),
    )
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(
            message="Generate a LinkedIn carousel on bond mistakes.",
            studio_panel=StudioPanelSelection(format="carousel", platform_preset="linkedin", file_type="pdf"),
        ),
    )

    assert assistant.content_version_id == content_version.id
    assert assistant.structured_payload["mode"] == "visual_generation"
    chat.content.generate.assert_awaited()


@pytest.mark.asyncio
async def test_chat_service_overrides_social_post_text_intent_when_visual_panel_is_explicit() -> None:
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={},
        is_active=True,
    )
    content_version = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Create a LinkedIn post about FD Bonds.",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "FD Bonds, explained", "body": "Body copy", "cta": "Read more"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="content_only",
            deliverable_type="linkedin_post",
            reason="text_deliverable",
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(generate=AsyncMock(), evaluate=AsyncMock())
    chat.content = SimpleNamespace(
        generate=AsyncMock(return_value=content_version),
        export=AsyncMock(return_value={"export_assets": [], "renderer_metadata": {}, "preview_asset": None}),
    )
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(
            message="Create a LinkedIn post about FD Bonds.",
            studio_panel=StudioPanelSelection(format="static", platform_preset="linkedin", file_type="png"),
            generate_image=True,
        ),
    )

    assert assistant.structured_payload["mode"] == "visual_generation"
    chat.content.generate.assert_awaited()
    chat.text_content.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_service_uses_text_rewrite_for_content_follow_ups() -> None:
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={
            "last_response_mode": "content_only",
            "last_content_version_id": str(uuid4()),
            "last_text_deliverable_type": "linkedin_post",
        },
        is_active=True,
    )
    rewritten = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Make it more analytical",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "Sharper hook", "body": "Rewritten body", "cta": "Read more"},
        blueprint_payload={},
        explainability_metadata={"retrieval_channels": ["knowledge"]},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="content_only",
            deliverable_type="linkedin_post",
            reason="content_rewrite_follow_up",
            uses_previous_output=True,
            revision_scope={"targeted_fields": ["cta"], "change_tone": True, "only_targeted": True},
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(
        generate=AsyncMock(),
        rewrite=AsyncMock(
            return_value=TextGenerationResult(
                content_version=rewritten,
                assistant_payload={"mode": "content_only", "deliverable_type": "linkedin_post", "generated_payload": rewritten.generated_payload},
                assistant_text="Sharper hook\n\nRewritten body\n\nRead more",
            )
        ),
        evaluate=AsyncMock(),
    )
    chat.content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), export=AsyncMock())
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(message="Make it more analytical"),
    )

    assert assistant.content_version_id == rewritten.id
    chat.text_content.rewrite.assert_awaited()
    chat.text_content.generate.assert_not_awaited()
    chat.content.rewrite.assert_not_awaited()
    rewrite_kwargs = chat.text_content.rewrite.await_args.kwargs
    assert rewrite_kwargs["revision_scope"]["targeted_fields"] == ["cta"]
    assert rewrite_kwargs["revision_scope"]["change_tone"] is True


@pytest.mark.asyncio
async def test_chat_service_uses_visual_rewrite_for_visual_follow_ups() -> None:
    previous_content_version_id = uuid4()
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "pdf"},
        conversational_context={
            "last_response_mode": "visual_generation",
            "last_content_version_id": str(previous_content_version_id),
        },
        is_active=True,
    )
    rewritten = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Make slide 2 sharper",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "Top Bond Mistakes", "body": "Updated slide content", "cta": "Explore Jiraaf"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="visual_generation",
            reason="visual_follow_up_reference",
            uses_previous_output=True,
            revision_scope={"slide_indexes": [2], "preserve_visuals": True},
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), evaluate=AsyncMock())
    chat.content = SimpleNamespace(
        generate=AsyncMock(),
        rewrite=AsyncMock(return_value=rewritten),
        export=AsyncMock(return_value={"export_assets": [], "renderer_metadata": {}, "preview_asset": None}),
    )
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(
            message="Make slide 2 sharper",
            studio_panel=StudioPanelSelection(format="carousel", platform_preset="linkedin", file_type="pdf"),
        ),
    )

    assert assistant.content_version_id == rewritten.id
    chat.content.rewrite.assert_awaited()
    chat.content.generate.assert_not_awaited()
    chat.content.export.assert_awaited()
    rewrite_kwargs = chat.content.rewrite.await_args.kwargs
    assert rewrite_kwargs["payload"].revision_scope["slide_indexes"] == [2]
    assert rewrite_kwargs["payload"].revision_scope["preserve_visuals"] is True


@pytest.mark.asyncio
async def test_chat_service_uses_visual_regenerate_for_broad_visual_follow_ups() -> None:
    previous_content_version_id = uuid4()
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={
            "last_response_mode": "visual_generation",
            "last_content_version_id": str(previous_content_version_id),
        },
        is_active=True,
    )
    previous_content = ContentVersion(
        id=previous_content_version_id,
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Write a LinkedIn carousel about bond duration.",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "Original", "body": "Body", "cta": "Explore"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    regenerated = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Regenerated prompt",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "New", "body": "Body", "cta": "Explore"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="visual_generation",
            reason="visual_rewrite_follow_up",
            uses_previous_output=True,
            revision_scope={
                "targeted_fields": [],
                "slide_indexes": [],
                "slide_targets": [],
                "preserve_visuals": False,
                "preserve_copy": False,
                "change_layout": False,
                "change_tone": True,
                "only_targeted": False,
            },
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), evaluate=AsyncMock())
    chat.contents = SimpleNamespace(get_scoped=AsyncMock(return_value=previous_content))
    chat.content = SimpleNamespace(
        generate=AsyncMock(return_value=regenerated),
        rewrite=AsyncMock(),
        export=AsyncMock(return_value={"export_assets": [], "renderer_metadata": {}, "preview_asset": None}),
    )
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(
            message="Make it more conversational and sharper.",
            studio_panel=StudioPanelSelection(format="carousel", platform_preset="linkedin", file_type="png"),
        ),
    )

    assert assistant.content_version_id == regenerated.id
    chat.content.generate.assert_awaited()
    chat.content.rewrite.assert_not_awaited()
    chat.content.export.assert_awaited()
    generate_kwargs = chat.content.generate.await_args.kwargs
    assert "Revise the existing creative with this instruction" in generate_kwargs["payload"].prompt


@pytest.mark.asyncio
async def test_chat_service_uses_visual_regenerate_for_global_headline_body_rewrites() -> None:
    previous_content_version_id = uuid4()
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={
            "last_response_mode": "visual_generation",
            "last_content_version_id": str(previous_content_version_id),
        },
        is_active=True,
    )
    previous_content = ContentVersion(
        id=previous_content_version_id,
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Write a LinkedIn carousel about bond duration.",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "Original", "body": "Body", "cta": "Explore"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    regenerated = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Regenerated prompt",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "New", "body": "Body", "cta": "Explore"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="visual_generation",
            reason="visual_rewrite_follow_up",
            uses_previous_output=True,
            revision_scope={
                "targeted_fields": ["body", "headline"],
                "slide_indexes": [],
                "slide_targets": [],
                "preserve_visuals": False,
                "preserve_copy": False,
                "change_layout": False,
                "change_tone": True,
                "only_targeted": True,
            },
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), evaluate=AsyncMock())
    chat.contents = SimpleNamespace(get_scoped=AsyncMock(return_value=previous_content))
    chat.content = SimpleNamespace(
        generate=AsyncMock(return_value=regenerated),
        rewrite=AsyncMock(),
        export=AsyncMock(return_value={"export_assets": [], "renderer_metadata": {}, "preview_asset": None}),
    )
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(
            message="Make the headline and body more conversational and sharper.",
            studio_panel=StudioPanelSelection(format="carousel", platform_preset="linkedin", file_type="png"),
        ),
    )

    assert assistant.content_version_id == regenerated.id
    chat.content.generate.assert_awaited()
    chat.content.rewrite.assert_not_awaited()
    generate_kwargs = chat.content.generate.await_args.kwargs
    assert generate_kwargs["payload"].request_mode == "variant_of_previous"
    assert generate_kwargs["payload"].source_content_version_id == previous_content_version_id


@pytest.mark.asyncio
async def test_chat_service_resets_distinct_visual_topic_instead_of_reusing_previous_prompt() -> None:
    previous_content_version_id = uuid4()
    previous_template_id = uuid4()
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={
            "last_response_mode": "visual_generation",
            "last_content_version_id": str(previous_content_version_id),
        },
        is_active=True,
    )
    previous_content = ContentVersion(
        id=previous_content_version_id,
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="create a post for Women Borrowers are reshaping the credit market in India.",
        studio_panel=session.studio_panel,
        generated_payload={
            "headline": "Women borrowers are reshaping the credit market",
            "body": "Earlier visual copy",
            "cta": "Explore",
        },
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
        selected_template_id=previous_template_id,
    )
    regenerated = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Write a LinkedIn carousel about the India-New Zealand FTA.",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "New", "body": "Body", "cta": "Explore"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="visual_generation",
            reason="visual_rewrite_follow_up",
            uses_previous_output=True,
            revision_scope={
                "targeted_fields": [],
                "slide_indexes": [],
                "slide_targets": [],
                "preserve_visuals": False,
                "preserve_copy": False,
                "change_layout": False,
                "change_tone": True,
                "only_targeted": False,
            },
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), evaluate=AsyncMock())
    chat.contents = SimpleNamespace(get_scoped=AsyncMock(return_value=previous_content))
    chat.content = SimpleNamespace(
        generate=AsyncMock(return_value=regenerated),
        rewrite=AsyncMock(),
        export=AsyncMock(return_value={"export_assets": [], "renderer_metadata": {}, "preview_asset": None}),
    )
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    prompt = (
        "Write a LinkedIn carousel for Jiraaf, an Indian alternative investments platform, "
        "on the India-New Zealand Free Trade Agreement signed on 27 April 2026."
    )
    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(
            message=prompt,
            studio_panel=StudioPanelSelection(format="carousel", platform_preset="linkedin", file_type="png"),
        ),
    )

    assert assistant.content_version_id == regenerated.id
    chat.content.generate.assert_awaited()
    chat.content.rewrite.assert_not_awaited()
    generate_kwargs = chat.content.generate.await_args.kwargs
    assert generate_kwargs["payload"].prompt == prompt
    assert "Women Borrowers" not in generate_kwargs["payload"].prompt
    assert generate_kwargs["payload"].template_id is None
    assert generate_kwargs["payload"].request_mode == "new_content"
    assert generate_kwargs["payload"].source_content_version_id is None


def test_chat_service_compose_visual_regeneration_prompt_uses_base_prompt_only_once() -> None:
    previous_content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt=(
            "create a post for Women Borrowers are reshaping the credit market in India.\n\n"
            "Revise the existing creative with this instruction: Write a LinkedIn carousel about the India-New Zealand FTA.\n"
            "Treat this as a fresh full visual regeneration that keeps the same topic and format while applying the revision."
        ),
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        generated_payload={},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )

    prompt = ChatService._compose_visual_regeneration_prompt(
        previous_content,
        "Make it more analytical.",
    )

    assert prompt.startswith("create a post for Women Borrowers are reshaping the credit market in India.")
    assert prompt.count("Revise the existing creative with this instruction:") == 1
    assert "India-New Zealand FTA" not in prompt
    assert prompt.endswith(
        "Treat this as a fresh full visual regeneration that keeps the same topic and format while applying the revision."
    )


def test_chat_service_detects_long_standalone_visual_brief_as_distinct_topic() -> None:
    previous_content = ContentVersion(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        session_id=uuid4(),
        created_by=uuid4(),
        prompt="Write a LinkedIn carousel for Jiraaf about the India-New Zealand Free Trade Agreement.",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "png"},
        generated_payload={
            "headline": "What's really inside the India-New Zealand Free Trade Deal?",
            "body": "Earlier slide body",
            "cta": "Explore Jiraaf",
        },
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )

    is_distinct = ChatService._looks_like_distinct_new_visual_topic(
        previous_content,
        (
            "Create a LinkedIn carousel post for Jiraaf on the topic: How Census 2027 could impact India's "
            "financial future. Keep it insightful but simple, connect it to money, infrastructure, and credit access."
        ),
        revision_scope=None,
    )

    assert is_distinct is True


@pytest.mark.asyncio
async def test_chat_service_stores_evaluation_context_for_follow_ups() -> None:
    reviewed_asset_id = uuid4()
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={},
        is_active=True,
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(route=lambda message, context: ChatIntentDecision(mode="evaluation", reason="evaluation_keywords"))
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(
        generate=AsyncMock(),
        rewrite=AsyncMock(),
        evaluate=AsyncMock(
            return_value={
                "mode": "evaluation",
                "review_type": "asset_tone_brand_consistency",
                "evaluation_scope": "asset_backed",
                "summary": "Tone score: 81/100. Asset-backed review coverage: 100/100.",
                "reviewed_asset_ids": [str(reviewed_asset_id)],
                "scorecard": {"overall_score": 81, "asset_coverage_score": 100},
            }
        ),
    )
    chat.content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), export=AsyncMock())
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(message="Check tone consistency", reference_asset_ids=[reviewed_asset_id]),
    )

    assert assistant.structured_payload["review_type"] == "asset_tone_brand_consistency"
    assert session.conversational_context["last_evaluation_review_type"] == "asset_tone_brand_consistency"
    assert session.conversational_context["last_evaluation_scope"] == "asset_backed"
    assert session.conversational_context["last_evaluation_score"] == 81
    assert session.conversational_context["last_reviewed_asset_ids"] == [str(reviewed_asset_id)]
    assert session.conversational_context["artifact_state"]["evaluation_history"][-1]["overall_score"] == 81


@pytest.mark.asyncio
async def test_chat_service_repuposes_previous_text_into_visual_generation() -> None:
    previous_content_version_id = uuid4()
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={
            "last_response_mode": "content_only",
            "last_non_evaluation_response_mode": "content_only",
            "last_text_output": "Bond ladders help reduce reinvestment risk through staggered maturities.",
            "last_text_deliverable_type": "linkedin_post",
            "last_content_version_id": str(previous_content_version_id),
            "last_non_evaluation_content_version_id": str(previous_content_version_id),
        },
        is_active=True,
    )
    content_version = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Turn it into a carousel",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "pdf"},
        generated_payload={"headline": "Bond ladders", "body": "Slide body", "cta": "Explore Jiraaf"},
        blueprint_payload={},
        explainability_metadata={},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="visual_generation",
            reason="repurpose_text_to_visual",
            uses_previous_output=False,
            workflow_plan={"type": "repurpose_text_to_visual", "target_mode": "visual_generation"},
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), evaluate=AsyncMock())
    chat.content = SimpleNamespace(
        generate=AsyncMock(return_value=content_version),
        rewrite=AsyncMock(),
        export=AsyncMock(return_value={"export_assets": [], "renderer_metadata": {}, "preview_asset": None}),
    )
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(
            message="Turn it into a carousel for LinkedIn.",
            studio_panel=StudioPanelSelection(format="carousel", platform_preset="linkedin", file_type="pdf"),
        ),
    )

    assert assistant.structured_payload["mode"] == "visual_generation"
    chat.content.generate.assert_awaited()
    generate_kwargs = chat.content.generate.await_args.kwargs
    assert "Source text to repurpose into a visual deliverable" in generate_kwargs["payload"].prompt
    assert "Bond ladders help reduce reinvestment risk" in generate_kwargs["payload"].prompt


@pytest.mark.asyncio
async def test_chat_service_reviews_document_then_generates_post() -> None:
    reviewed_asset_id = uuid4()
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={},
        is_active=True,
    )
    content_version = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Review this document, then generate a LinkedIn post from it.",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "FTA structure", "body": "Body copy", "cta": "Read more"},
        blueprint_payload={},
        explainability_metadata={"retrieval_channels": ["knowledge"]},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="content_only",
            deliverable_type="linkedin_post",
            reason="review_then_generate",
            workflow_plan={"type": "review_then_generate", "target_mode": "content_only"},
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(
        evaluate=AsyncMock(
            return_value={
                "summary": "The source document is strong on policy structure but needs a clearer strategic takeaway.",
                "reviewed_asset_ids": [str(reviewed_asset_id)],
                "scorecard": {"overall_score": 78},
            }
        ),
        generate=AsyncMock(
            return_value=TextGenerationResult(
                content_version=content_version,
                assistant_payload={"mode": "content_only", "deliverable_type": "linkedin_post", "generated_payload": content_version.generated_payload},
                assistant_text="FTA structure\n\nBody copy\n\nRead more",
            )
        ),
        rewrite=AsyncMock(),
    )
    chat.content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), export=AsyncMock())
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(
            message="Review this document, then generate a LinkedIn post from it.",
            reference_asset_ids=[reviewed_asset_id],
        ),
    )

    assert assistant.structured_payload["mode"] == "content_only"
    chat.text_content.evaluate.assert_awaited()
    chat.text_content.generate.assert_awaited()
    generate_kwargs = chat.text_content.generate.await_args.kwargs
    assert "Review findings to use as source guidance" in generate_kwargs["prompt"]
    assert "needs a clearer strategic takeaway" in generate_kwargs["prompt"]


@pytest.mark.asyncio
async def test_chat_service_applies_last_review_to_rewrite() -> None:
    previous_content_version_id = uuid4()
    session = ContentSession(
        id=uuid4(),
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        title="Chat Session",
        session_kind="chat",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        conversational_context={
            "last_response_mode": "evaluation",
            "last_non_evaluation_response_mode": "content_only",
            "last_content_version_id": str(previous_content_version_id),
            "last_non_evaluation_content_version_id": str(previous_content_version_id),
            "last_text_deliverable_type": "linkedin_post",
            "last_evaluation_summary": "The draft is clear but too promotional. Make it more analytical and less salesy.",
        },
        is_active=True,
    )
    rewritten = ContentVersion(
        id=uuid4(),
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        session_id=session.id,
        created_by=session.user_id,
        prompt="Rewrite this based on review.",
        studio_panel=session.studio_panel,
        generated_payload={"headline": "Sharper hook", "body": "Rewritten body", "cta": "Read more"},
        blueprint_payload={},
        explainability_metadata={"retrieval_channels": ["knowledge"]},
        tone_feedback={},
    )
    chat = ChatService.__new__(ChatService)
    chat.session = SimpleNamespace(commit=AsyncMock())
    chat.messages = SimpleNamespace(add=AsyncMock())
    chat.get_session = AsyncMock(return_value=session)
    chat.intent_router = SimpleNamespace(
        route=lambda message, context: ChatIntentDecision(
            mode="content_only",
            deliverable_type="linkedin_post",
            reason="apply_last_review",
            uses_previous_output=True,
            revision_scope={"change_tone": True},
            workflow_plan={"type": "apply_last_review", "target_mode": "content_only", "uses_previous_output": True},
        )
    )
    chat.conversation = SimpleNamespace(reply=lambda **kwargs: pytest.fail("conversation path should not run"))
    chat.text_content = SimpleNamespace(
        generate=AsyncMock(),
        rewrite=AsyncMock(
            return_value=TextGenerationResult(
                content_version=rewritten,
                assistant_payload={"mode": "content_only", "deliverable_type": "linkedin_post", "generated_payload": rewritten.generated_payload},
                assistant_text="Sharper hook\n\nRewritten body\n\nRead more",
            )
        ),
        evaluate=AsyncMock(),
    )
    chat.content = SimpleNamespace(generate=AsyncMock(), rewrite=AsyncMock(), export=AsyncMock())
    chat.assets = SimpleNamespace(list_by_content=AsyncMock(return_value=[]))
    chat.brands = SimpleNamespace(get_scoped=AsyncMock(return_value=SimpleNamespace(name="Jiraaf")))

    _, assistant = await chat.send_message(
        tenant_id=session.tenant_id,
        brand_space_id=session.brand_space_id,
        user_id=session.user_id,
        session_id=session.id,
        payload=ChatMessageCreateRequest(message="Rewrite this based on review."),
    )

    assert assistant.content_version_id == rewritten.id
    chat.text_content.rewrite.assert_awaited()
    rewrite_kwargs = chat.text_content.rewrite.await_args.kwargs
    assert "Use these review findings while rewriting" in rewrite_kwargs["rewrite_instruction"]
    assert "too promotional" in rewrite_kwargs["rewrite_instruction"]
