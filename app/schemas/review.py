from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, AssetReference


class ShareLinkCreateRequest(APIModel):
    content_version_id: UUID
    title: str | None = None
    allow_external_comments: bool = True


class ReviewCommentCreateRequest(APIModel):
    body: str = Field(min_length=1)
    external_author_name: str | None = None


class ReviewStatusUpdateRequest(APIModel):
    status: str


class ReviewLinkResponse(APIModel):
    id: UUID
    token: str
    status: str
    allow_external_comments: bool


class ReviewCommentResponse(APIModel):
    id: UUID
    body: str
    external_author_name: str | None = None
    author_user_id: UUID | None = None


class ReviewDetailContent(APIModel):
    id: UUID
    title: str | None = None
    generated_payload: dict
    blueprint_payload: dict
    generation_decision: dict = Field(default_factory=dict)
    assets: list[AssetReference] = Field(default_factory=list)


class ReviewDetailResponse(APIModel):
    link: ReviewLinkResponse
    content: ReviewDetailContent | None = None
    comments: list[ReviewCommentResponse] = Field(default_factory=list)
