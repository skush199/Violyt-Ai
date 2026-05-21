from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_brand_access, get_brand_scope_header, get_current_principal, require_brand_scope
from app.db.session import get_db_session
from app.schemas.knowledge import KnowledgeAssetResponse, KnowledgeReprocessRequest, KnowledgeUploadRequest
from app.services.asset_delivery import AssetDeliveryService
from app.services.knowledge import KnowledgeService


router = APIRouter()


def serialize_asset(asset) -> KnowledgeAssetResponse:
    delivery = AssetDeliveryService()
    response = KnowledgeAssetResponse.model_validate(asset)
    return response.model_copy(
        update={
            "asset_url": delivery.build_signed_url(
                storage_path=asset.storage_path,
                filename=asset.original_filename,
            )
        }
    )


@router.post("/upload", response_model=KnowledgeAssetResponse)
async def upload_knowledge(
    payload: KnowledgeUploadRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeAssetResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    asset = await KnowledgeService(session).upload(principal.tenant_id, brand_scope, payload)
    return serialize_asset(asset)


@router.get("/list", response_model=list[KnowledgeAssetResponse])
async def list_knowledge(
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[KnowledgeAssetResponse]:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    assets = await KnowledgeService(session).list(principal.tenant_id, brand_scope)
    return [serialize_asset(item) for item in assets]


@router.get("/{knowledge_id}/status", response_model=KnowledgeAssetResponse)
async def knowledge_status(
    knowledge_id: UUID,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeAssetResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    asset = await KnowledgeService(session).get_scoped(principal.tenant_id, brand_scope, knowledge_id)
    return serialize_asset(asset)


@router.delete("/{knowledge_id}", response_model=KnowledgeAssetResponse)
async def delete_knowledge(
    knowledge_id: UUID,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeAssetResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    asset = await KnowledgeService(session).delete_scoped(principal.tenant_id, brand_scope, knowledge_id)
    return serialize_asset(asset)


@router.post("/{knowledge_id}/reprocess", response_model=KnowledgeAssetResponse)
async def reprocess_knowledge(
    knowledge_id: UUID,
    payload: KnowledgeReprocessRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeAssetResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    asset = await KnowledgeService(session).reprocess_scoped(principal.tenant_id, brand_scope, knowledge_id)
    return serialize_asset(asset)
