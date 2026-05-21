from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_brand_access, get_brand_scope_header, get_current_principal, require_brand_scope
from app.db.session import get_db_session
from app.schemas.common import MessageResponse
from app.schemas.template import (
    TemplateApplyRequest,
    TemplateMetadataUpsertRequest,
    TemplateRecommendRequest,
    TemplateRecommendationResponse,
    TemplateResponse,
    TemplateUploadRequest,
)
from app.services.asset_delivery import AssetDeliveryService
from app.services.template import TemplateService


router = APIRouter()


def serialize_template(template) -> TemplateResponse:
    delivery = AssetDeliveryService()
    download_name = f"{template.name}{Path(template.storage_path).suffix}"
    response = TemplateResponse.model_validate(template)
    return response.model_copy(
        update={
            "asset_url": delivery.build_signed_url(
                storage_path=template.storage_path,
                filename=download_name,
            )
        }
    )


def serialize_template_metadata(metadata) -> dict:
    if not metadata:
        return {}
    return {
        "id": str(metadata.id),
        "template_id": str(metadata.template_id),
        "zone_map": metadata.zone_map,
        "sizing_rules": metadata.sizing_rules,
        "platform_rules": metadata.platform_rules,
        "editable_fields": metadata.editable_fields,
        "export_rules": metadata.export_rules,
    }


@router.post("/upload", response_model=TemplateResponse)
async def upload_template(
    payload: TemplateUploadRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TemplateResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    template = await TemplateService(session).upload(principal.tenant_id, brand_scope, payload)
    return serialize_template(template)


@router.get("/list", response_model=list[TemplateResponse])
async def list_templates(
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[TemplateResponse]:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    templates = await TemplateService(session).list(principal.tenant_id, brand_scope)
    return [serialize_template(item) for item in templates]


@router.get("/{template_id}", response_model=dict)
async def template_detail(
    template_id: UUID,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    template, metadata = await TemplateService(session).detail(principal.tenant_id, brand_scope, template_id)
    return {
        "template": serialize_template(template).model_dump(),
        "metadata": serialize_template_metadata(metadata),
    }


@router.put("/{template_id}/metadata", response_model=dict)
async def update_metadata(
    template_id: UUID,
    payload: TemplateMetadataUpsertRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    metadata = await TemplateService(session).update_metadata(principal.tenant_id, brand_scope, template_id, payload)
    return serialize_template_metadata(metadata)


@router.post("/apply", response_model=dict)
async def apply_template(
    payload: TemplateApplyRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    template, metadata = await TemplateService(session).detail(principal.tenant_id, brand_scope, payload.template_id)
    return {
        "template": serialize_template(template).model_dump(),
        "metadata": serialize_template_metadata(metadata),
        "prompt": payload.prompt,
        "studio_panel": payload.studio_panel,
    }


@router.post("/recommend", response_model=list[TemplateRecommendationResponse])
async def recommend_templates(
    payload: TemplateRecommendRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[TemplateRecommendationResponse]:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    return await TemplateService(session).recommend(
        tenant_id=principal.tenant_id,
        brand_space_id=brand_scope,
        prompt=payload.prompt,
        studio_panel=payload.studio_panel,
        limit=payload.limit,
    )


@router.delete("/{template_id}", response_model=MessageResponse)
async def delete_template(
    template_id: UUID,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    await TemplateService(session).delete(principal.tenant_id, brand_scope, template_id)
    return MessageResponse(message="Template deleted")
