from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, StudioPanelSelection


class ChatSessionCreateRequest(APIModel):
    title: str | None = None
    studio_panel: StudioPanelSelection


class ChatMessageCreateRequest(APIModel):
    message: str = Field(min_length=1)
    studio_panel: StudioPanelSelection | None = None
    persona_id: UUID | None = None
    objective_id: UUID | None = None
    template_id: UUID | None = None
    reference_asset_ids: list[UUID] = Field(default_factory=list)
    generate_image: bool = True


class ChatSessionResponse(APIModel):
    id: UUID
    brand_space_id: UUID | None = None
    title: str | None = None
    session_kind: str
    studio_panel: dict
    conversational_context: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(APIModel):
    id: UUID
    session_id: UUID
    user_id: UUID | None = None
    content_version_id: UUID | None = None
    role: str
    message_text: str
    structured_payload: dict
    citations: list[dict]
    created_at: datetime


class ChatSendResponse(APIModel):
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
