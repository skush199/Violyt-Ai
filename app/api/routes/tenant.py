from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_tenant_access, get_current_principal, require_roles
from app.core.enums import RoleCode
from app.db.session import get_db_session
from app.schemas.common import MessageResponse
from app.schemas.tenant import (
    TenantCreateRequest,
    TenantCreateResponse,
    TenantLogoUploadRequest,
    TenantBrandSpaceSummaryResponse,
    TenantResponse,
    TenantSummaryResponse,
    TenantUpdateRequest,
    TenantUsageLimitUpdate,
    TenantUsageSummary,
    TenantUserCreateRequest,
    TenantUserCreateResponse,
    TenantUserResponse,
    TenantUserUpdateRequest,
)
from app.services.tenant import TenantService


router = APIRouter()


@router.post("", response_model=TenantCreateResponse, dependencies=[Depends(require_roles(RoleCode.SUPER_ADMIN))])
async def create_tenant(
    payload: TenantCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TenantCreateResponse:
    tenant, delivery = await TenantService(session).create_tenant(payload)
    return TenantCreateResponse.model_validate(
        {
            **TenantResponse.model_validate(tenant).model_dump(),
            "activation_email": {
                "attempted": delivery.attempted,
                "delivered": delivery.delivered,
                "recipient_email": delivery.recipient_email,
                "reason": delivery.reason,
            },
        }
    )


@router.get("", response_model=list[TenantSummaryResponse], dependencies=[Depends(require_roles(RoleCode.SUPER_ADMIN))])
async def list_tenants(session: AsyncSession = Depends(get_db_session)) -> list[TenantSummaryResponse]:
    service = TenantService(session)
    tenants = await service.list_tenants()
    summaries = [await service.get_tenant_summary(tenant.id) for tenant in tenants]
    return [TenantSummaryResponse.model_validate(item) for item in summaries]


@router.get("/{tenant_id}", response_model=TenantSummaryResponse)
async def get_tenant(
    tenant_id: UUID,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSummaryResponse:
    assert_tenant_access(principal, tenant_id)
    summary = await TenantService(session).get_tenant_summary(tenant_id)
    return TenantSummaryResponse.model_validate(summary)


@router.post("/{tenant_id}/logo", response_model=TenantSummaryResponse)
async def upload_tenant_logo(
    tenant_id: UUID,
    payload: TenantLogoUploadRequest,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSummaryResponse:
    assert_tenant_access(principal, tenant_id)
    service = TenantService(session)
    await service.upload_logo(tenant_id, payload)
    summary = await service.get_tenant_summary(tenant_id)
    return TenantSummaryResponse.model_validate(summary)


@router.put("/{tenant_id}", response_model=TenantSummaryResponse)
async def update_tenant(
    tenant_id: UUID,
    payload: TenantUpdateRequest,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSummaryResponse:
    assert_tenant_access(principal, tenant_id)
    service = TenantService(session)
    await service.update_tenant(tenant_id, payload)
    summary = await service.get_tenant_summary(tenant_id)
    return TenantSummaryResponse.model_validate(summary)


@router.delete(
    "/{tenant_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_roles(RoleCode.SUPER_ADMIN))],
)
async def delete_tenant(
    tenant_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    await TenantService(session).delete_tenant(tenant_id)
    return MessageResponse(message="Tenant deleted")


@router.get("/{tenant_id}/users", response_model=list[TenantUserResponse])
async def list_users(
    tenant_id: UUID,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[TenantUserResponse]:
    assert_tenant_access(principal, tenant_id)
    service = TenantService(session)
    users = await service.list_users(tenant_id)
    enriched = [await service.build_user_summary(user) for user in users]
    return [TenantUserResponse.model_validate(item) for item in enriched]


@router.get("/{tenant_id}/brand-spaces", response_model=list[TenantBrandSpaceSummaryResponse])
async def list_tenant_brand_spaces(
    tenant_id: UUID,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[TenantBrandSpaceSummaryResponse]:
    assert_tenant_access(principal, tenant_id)
    service = TenantService(session)
    summaries = await service.list_tenant_brand_space_summaries(tenant_id)
    return [TenantBrandSpaceSummaryResponse.model_validate(item) for item in summaries]


@router.post("/{tenant_id}/users", response_model=TenantUserCreateResponse)
async def create_tenant_user(
    tenant_id: UUID,
    payload: TenantUserCreateRequest,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantUserCreateResponse:
    assert_tenant_access(principal, tenant_id)
    service = TenantService(session)
    user, delivery = await service.create_tenant_user(tenant_id, payload)
    summary = await service.build_user_summary(user)
    return TenantUserCreateResponse.model_validate(
        {
            **summary,
            "activation_email": {
                "attempted": delivery.attempted,
                "delivered": delivery.delivered,
                "recipient_email": delivery.recipient_email,
                "reason": delivery.reason,
            },
        }
    )


@router.get("/{tenant_id}/users/{user_id}", response_model=TenantUserResponse)
async def get_user(
    tenant_id: UUID,
    user_id: UUID,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantUserResponse:
    assert_tenant_access(principal, tenant_id)
    summary = await TenantService(session).get_user_summary(tenant_id, user_id)
    return TenantUserResponse.model_validate(summary)


@router.put("/{tenant_id}/users/{user_id}", response_model=TenantUserResponse)
async def update_user(
    tenant_id: UUID,
    user_id: UUID,
    payload: TenantUserUpdateRequest,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantUserResponse:
    assert_tenant_access(principal, tenant_id)
    service = TenantService(session)
    user = await service.update_tenant_user(tenant_id, user_id, payload)
    return TenantUserResponse.model_validate(await service.build_user_summary(user))


@router.post("/{tenant_id}/users/{user_id}/deactivate", response_model=MessageResponse)
async def deactivate_user(
    tenant_id: UUID,
    user_id: UUID,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    assert_tenant_access(principal, tenant_id)
    await TenantService(session).deactivate_user(tenant_id, user_id)
    return MessageResponse(message="User deactivated")


@router.put("/{tenant_id}/usage-limits", response_model=MessageResponse, dependencies=[Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN))])
async def update_usage_limits(
    tenant_id: UUID,
    payload: TenantUsageLimitUpdate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    assert_tenant_access(principal, tenant_id)
    await TenantService(session).update_usage_limits(tenant_id, payload)
    return MessageResponse(message="Usage limits updated")


@router.get("/{tenant_id}/usage-summary", response_model=TenantUsageSummary)
async def get_usage_summary(
    tenant_id: UUID,
    _: CurrentPrincipal = Depends(require_roles(RoleCode.SUPER_ADMIN, RoleCode.TENANT_ADMIN)),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantUsageSummary:
    assert_tenant_access(principal, tenant_id)
    summary = await TenantService(session).get_usage_summary(tenant_id)
    return TenantUsageSummary.model_validate(summary)
