from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    CurrentPrincipal,
    assert_brand_access,
    get_brand_scope_header,
    get_current_principal,
    require_brand_scope,
)
from app.db.session import get_db_session
from app.repositories.content import AssetRepository
from app.schemas.content import ContentCopyRequest, ContentExportRequest, ContentGenerateRequest, ContentRewriteRequest, ContentVersionResponse, ToneCheckRequest, ToneEvaluationResponse
from app.schemas.common import AssetReference
from app.schemas.render import RenderResponse
from app.services.content import ContentService


router = APIRouter()


def attach_assets(content, assets) -> ContentVersionResponse:
    response = ContentVersionResponse.model_validate(content)
    explainability = content.explainability_metadata or {}
    response.generation_decision = explainability.get("layout_decision", {})
    response.scene_graph = explainability.get("scene_graph", {})
    response.creative_decision = explainability.get("creative_decision", {}) or response.generation_decision
    response.validation_report = explainability.get("validation_report", {})
    response.repair_attempts = int(explainability.get("repair_attempts", 0) or 0)
    response.assets = [
        AssetReference(
            asset_id=item.id,
            mime_type=item.mime_type,
            storage_path=item.storage_path,
            width=item.width,
            height=item.height,
            asset_role=item.asset_role,
        )
        for item in assets
    ]
    return response


@router.post("/generate", response_model=ContentVersionResponse)
async def generate_content(
    payload: ContentGenerateRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContentVersionResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)

    service = ContentService(session)
    content = await service.generate(principal.tenant_id, brand_scope, principal.user_id, payload)
    assets = await AssetRepository(session).list_by_content(content.id)

    return attach_assets(content, assets)


@router.post("/rewrite", response_model=ContentVersionResponse)
async def rewrite_content(
    payload: ContentRewriteRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContentVersionResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)

    content = await ContentService(session).rewrite(principal.tenant_id, brand_scope, principal.user_id, payload)
    assets = await AssetRepository(session).list_by_content(content.id)

    return attach_assets(content, assets)


@router.post("/tone-check", response_model=ToneEvaluationResponse)
async def tone_check(
    payload: ToneCheckRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ToneEvaluationResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    result = await ContentService(session).tone_check(brand_scope, payload)
    return ToneEvaluationResponse(**result)


@router.get("/history", response_model=list[ContentVersionResponse])
async def content_history(
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[ContentVersionResponse]:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)

    service = ContentService(session)
    history = await service.history(principal.tenant_id, brand_scope)

    asset_repo = AssetRepository(session)
    items = []

    for content in history:
        assets = await asset_repo.list_by_content(content.id)
        items.append(attach_assets(content, assets))

    return items


@router.get("/{content_id}", response_model=ContentVersionResponse)
async def content_detail(
    content_id: UUID,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContentVersionResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)

    service = ContentService(session)
    content = await service.detail(principal.tenant_id, brand_scope, content_id)
    assets = await AssetRepository(session).list_by_content(content.id)

    return attach_assets(content, assets)


@router.post("/export", response_model=RenderResponse)
async def export_content(
    payload: ContentExportRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> RenderResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)

    response = await ContentService(session).export(
        principal.tenant_id,
        brand_scope,
        payload.content_version_id,
        (payload.studio_panel or {}) | {"file_type": payload.export_format},
        blueprint_payload=payload.blueprint_payload,
        template_id=payload.template_id,
    )

    return RenderResponse(content_version_id=payload.content_version_id, **response)


@router.post("/copy", response_model=dict)
async def copy_content(
    payload: ContentCopyRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)

    return await ContentService(session).copy(principal.tenant_id, brand_scope, payload.content_version_id)
