from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_brand_access, get_brand_scope_header, get_current_principal, require_brand_scope
from app.db.session import get_db_session
from app.repositories.knowledge import TemplateMetadataRepository, TemplateRepository
from app.repositories.content import ContentRepository
from app.schemas.render import RenderExportRequest, RenderLayoutRequest, RenderPreviewRequest, RenderResponse
from app.services.content import ContentService


router = APIRouter()


@router.post("/layout", response_model=dict)
async def render_layout(
    payload: RenderLayoutRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    content = await ContentRepository(session).get_scoped(payload.content_version_id, principal.tenant_id, brand_scope)
    if not content:
        raise HTTPException(status_code=404, detail="Content version not found")
    merged_panel = ContentService._merge_studio_panel(content.studio_panel, payload.studio_panel)
    template = await TemplateRepository(session).get_scoped(payload.template_id, principal.tenant_id, brand_scope) if payload.template_id else None
    template_meta = await TemplateMetadataRepository(session).get_by_template(template.id) if template else None
    blueprint = ContentService._resolve_blueprint_payload(
        stored_blueprint=content.blueprint_payload,
        template_zone_map=template_meta.zone_map if template_meta else None,
        override_blueprint=payload.blueprint_payload,
        studio_panel=merged_panel,
    )
    return {"content_version_id": str(content.id), "blueprint": blueprint, "studio_panel": merged_panel}


@router.post("/preview", response_model=RenderResponse)
async def render_preview(
    payload: RenderPreviewRequest,
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
        payload.studio_panel,
        blueprint_payload=payload.blueprint_payload,
        template_id=payload.template_id,
    )
    return RenderResponse(content_version_id=payload.content_version_id, **response)


@router.post("/export", response_model=RenderResponse)
async def render_export(
    payload: RenderExportRequest,
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
        payload.studio_panel | {"file_type": payload.export_format},
        blueprint_payload=payload.blueprint_payload,
        template_id=payload.template_id,
    )
    return RenderResponse(content_version_id=payload.content_version_id, **response)


@router.get("/{content_id}/status", response_model=dict)
async def render_status(
    content_id: UUID,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    content = await ContentRepository(session).get_scoped(content_id, principal.tenant_id, brand_scope)
    if not content:
        raise HTTPException(status_code=404, detail="Content version not found")
    return {"content_version_id": str(content.id), "status": "available", "has_blueprint": bool(content.blueprint_payload)}
