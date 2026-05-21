from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_brand_access, get_brand_scope_header, get_current_principal, require_brand_scope
from app.db.session import get_db_session
from app.schemas.common import MessageResponse
from app.schemas.social import SocialConnectRequest, SocialConnectionResponse, SocialPublishRequest
from app.services.social import SocialService


router = APIRouter()


@router.get("/list", response_model=list[SocialConnectionResponse])
async def list_social_connections(
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[SocialConnectionResponse]:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    items = await SocialService(session).list_connections(principal.tenant_id, brand_scope)
    return [SocialConnectionResponse.model_validate(item) for item in items]


@router.post("/connect", response_model=SocialConnectionResponse)
async def connect_social(
    payload: SocialConnectRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> SocialConnectionResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    connection = await SocialService(session).connect(principal.tenant_id, brand_scope, payload.platform, payload.account_name, payload.account_identifier, payload.access_token, payload.refresh_token, payload.scopes)
    return SocialConnectionResponse.model_validate(connection)


@router.post("/publish", response_model=dict)
async def publish_social(
    payload: SocialPublishRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    return await SocialService(session).publish(principal.tenant_id, brand_scope, payload.platform, payload.model_dump())


@router.post("/disconnect", response_model=MessageResponse)
async def disconnect_social(
    payload: SocialConnectRequest,
    brand_scope: UUID = Depends(get_brand_scope_header),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    brand_scope = require_brand_scope(brand_scope)
    assert_brand_access(principal, brand_scope)
    await SocialService(session).disconnect(brand_scope, payload.platform)
    return MessageResponse(message="Disconnected")
