from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_brand_access, get_current_principal, require_roles
from app.core.enums import RoleCode
from app.db.session import get_db_session
from app.schemas.analytics import AnalyticsResponse
from app.services.analytics import AnalyticsService


router = APIRouter()


@router.get("/platform", response_model=AnalyticsResponse)
async def platform_analytics(
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsResponse:
    metrics = await AnalyticsService(session).platform_summary()
    return AnalyticsResponse(scope="platform", metrics=metrics)


@router.get("/tenant", response_model=AnalyticsResponse)
async def tenant_analytics(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsResponse:
    if RoleCode.TENANT_USER in principal.role_codes or RoleCode.BRAND_USER in principal.role_codes:
        raise HTTPException(status_code=403, detail="Tenant-level analytics unavailable for this role")
    metrics = await AnalyticsService(session).tenant_summary(principal.tenant_id)
    return AnalyticsResponse(scope="tenant", tenant_id=principal.tenant_id, metrics=metrics)


@router.get("/brand/{brand_id}", response_model=AnalyticsResponse)
async def brand_analytics(
    brand_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsResponse:
    if RoleCode.BRAND_USER in principal.role_codes:
        raise HTTPException(status_code=403, detail="Brand analytics unavailable for this role")
    assert_brand_access(principal, brand_id)
    metrics = await AnalyticsService(session).brand_summary(principal.tenant_id, brand_id)
    return AnalyticsResponse(scope="brand", tenant_id=principal.tenant_id, brand_space_id=brand_id, metrics=metrics)


@router.get("/usage-summary", response_model=AnalyticsResponse)
async def usage_summary(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsResponse:
    if RoleCode.TENANT_USER in principal.role_codes or RoleCode.BRAND_USER in principal.role_codes:
        raise HTTPException(status_code=403, detail="Usage summary unavailable for this role")
    metrics = await AnalyticsService(session).tenant_summary(principal.tenant_id)
    return AnalyticsResponse(scope="usage_summary", tenant_id=principal.tenant_id, metrics=metrics["usage"])
