from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_brand_access, get_current_principal, get_brand_scope_header, require_brand_scope
from app.db.session import get_db_session
from app.repositories.content import AssetRepository, ContentRepository
from app.schemas.common import AssetReference
from app.schemas.review import (
    ReviewCommentCreateRequest,
    ReviewCommentResponse,
    ReviewDetailContent,
    ReviewDetailResponse,
    ReviewLinkResponse,
    ReviewStatusUpdateRequest,
    ShareLinkCreateRequest,
)
from app.services.review import ReviewService


router = APIRouter()


@router.post("/share-link", response_model=ReviewLinkResponse)
async def create_share_link(
    payload: ShareLinkCreateRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ReviewLinkResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    link = await ReviewService(session).create_link(principal.tenant_id, brand_scope, payload.content_version_id, principal.user_id, payload.title, payload.allow_external_comments)
    return ReviewLinkResponse.model_validate(link)


@router.get("/{token}", response_model=ReviewDetailResponse)
async def get_review(token: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    link, comments = await ReviewService(session).get_by_token(token)
    content = await ContentRepository(session).get_scoped(link.content_version_id, link.tenant_id, link.brand_space_id)
    assets = await AssetRepository(session).list_by_content(link.content_version_id)
    return ReviewDetailResponse(
        link=ReviewLinkResponse.model_validate(link).model_dump(),
        content=ReviewDetailContent(
            id=content.id,
            title=content.title,
            generated_payload=content.generated_payload,
            blueprint_payload=content.blueprint_payload,
            generation_decision=content.explainability_metadata.get("layout_decision", {}),
            assets=[
                AssetReference(
                    asset_id=item.id,
                    mime_type=item.mime_type,
                    storage_path=item.storage_path,
                    width=item.width,
                    height=item.height,
                    asset_role=item.asset_role,
                )
                for item in assets
            ],
        ) if content else None,
        comments=[
            ReviewCommentResponse(
                id=item.id,
                body=item.body,
                external_author_name=item.external_author_name,
                author_user_id=item.author_user_id,
            )
            for item in comments
        ],
    )


@router.post("/{token}/comment", response_model=ReviewCommentResponse)
async def add_comment(token: str, payload: ReviewCommentCreateRequest, session: AsyncSession = Depends(get_db_session)) -> dict:
    service = ReviewService(session)
    link, _ = await service.get_by_token(token)
    comment = await service.add_comment(link.id, link.tenant_id, link.brand_space_id, payload.body, None, payload.external_author_name)
    return ReviewCommentResponse(
        id=comment.id,
        body=comment.body,
        external_author_name=comment.external_author_name,
        author_user_id=comment.author_user_id,
    )


@router.post("/{token}/status", response_model=ReviewLinkResponse)
async def update_review_status(token: str, payload: ReviewStatusUpdateRequest, session: AsyncSession = Depends(get_db_session)) -> ReviewLinkResponse:
    service = ReviewService(session)
    link, _ = await service.get_by_token(token)
    updated = await service.update_status(link.id, payload.status)
    return ReviewLinkResponse.model_validate(updated)
