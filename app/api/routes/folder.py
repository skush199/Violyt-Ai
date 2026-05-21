from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_brand_access, get_brand_scope_header, get_current_principal, require_brand_scope
from app.db.session import get_db_session
from app.schemas.common import MessageResponse
from app.schemas.folder import FolderCreateRequest, FolderMoveRequest, FolderRenameRequest
from app.services.folder import FolderService


router = APIRouter()


@router.post("", response_model=dict)
async def create_folder(
    payload: FolderCreateRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    folder = await FolderService(session).create(principal.tenant_id, brand_scope, principal.user_id, payload.name, payload.description)
    return {"id": folder.id, "name": folder.name, "description": folder.description}


@router.get("", response_model=list[dict])
async def list_folders(
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    folders = await FolderService(session).list(principal.tenant_id, brand_scope)
    return [{"id": item.id, "name": item.name, "description": item.description} for item in folders]


@router.put("/{folder_id}", response_model=dict)
async def rename_folder(
    folder_id: UUID,
    payload: FolderRenameRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    folder = await FolderService(session).rename_scoped(principal.tenant_id, brand_scope, folder_id, payload.name)
    return {"id": folder.id, "name": folder.name}


@router.delete("/{folder_id}", response_model=MessageResponse)
async def delete_folder(
    folder_id: UUID,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    await FolderService(session).delete_scoped(principal.tenant_id, brand_scope, folder_id)
    return MessageResponse(message="Folder deleted")


@router.post("/move", response_model=MessageResponse)
async def move_content(
    payload: FolderMoveRequest,
    brand_scope = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    await FolderService(session).move_content_scoped(principal.tenant_id, brand_scope, payload.content_version_id, payload.folder_id)
    return MessageResponse(message="Content moved")
