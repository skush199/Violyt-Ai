from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class SocialConnectRequest(APIModel):
    platform: str
    account_name: str | None = None
    account_identifier: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    scopes: list[str] = Field(default_factory=list)


class SocialPublishRequest(APIModel):
    content_version_id: UUID
    platform: str
    caption_override: str | None = None
    media_asset_ids: list[UUID] = Field(default_factory=list)
    publish_now: bool = Field(default=True)


class SocialConnectionResponse(APIModel):
    id: UUID
    platform: str
    account_name: str | None = None
    account_identifier: str | None = None
    is_connected: bool
