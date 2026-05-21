from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.schemas.auth import (
    ActivationRequest,
    AuthLoginResponse,
    ChangePasswordRequest,
    CurrentUserResponse,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordResetResponse,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenPairResponse,
    TwoFactorCodeRequest,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
)
from app.schemas.common import MessageResponse
from app.services.auth import AuthService


router = APIRouter()


@router.post("/login", response_model=AuthLoginResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> AuthLoginResponse:
    return await AuthService(session).login(payload.email, payload.password)


@router.post("/activate", response_model=TokenPairResponse)
async def activate(payload: ActivationRequest, session: AsyncSession = Depends(get_db_session)) -> TokenPairResponse:
    return await AuthService(session).activate(payload.token, payload.password)


@router.post("/forgot-password", response_model=PasswordResetResponse)
async def forgot_password(payload: ForgotPasswordRequest, session: AsyncSession = Depends(get_db_session)) -> PasswordResetResponse:
    return await AuthService(session).forgot_password(payload.email)


@router.post("/reset-password", response_model=TokenPairResponse)
async def reset_password(payload: ResetPasswordRequest, session: AsyncSession = Depends(get_db_session)) -> TokenPairResponse:
    return await AuthService(session).reset_password(payload.token, payload.password)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(payload: RefreshTokenRequest, session: AsyncSession = Depends(get_db_session)) -> TokenPairResponse:
    return await AuthService(session).refresh_access_token(payload.refresh_token)


@router.get("/me", response_model=CurrentUserResponse)
async def me(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUserResponse:
    return await AuthService(session).build_current_user_response(
        principal.user_id,
        sorted(principal.role_codes),
        list(principal.brand_space_ids),
    )


@router.get("/profile", response_model=CurrentUserResponse)
async def profile(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUserResponse:
    return await AuthService(session).build_current_user_response(
        principal.user_id,
        sorted(principal.role_codes),
        list(principal.brand_space_ids),
    )


@router.put("/profile", response_model=CurrentUserResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUserResponse:
    user = await AuthService(session).update_profile(
        principal.user_id,
        payload.full_name,
        payload.email,
        payload.phone_number,
        payload.notifications_enabled,
    )
    return CurrentUserResponse(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        email=user.email,
        role_codes=sorted(principal.role_codes),
        assigned_brand_space_ids=list(principal.brand_space_ids),
        full_name=user.full_name,
        extra={
            "phone_number": user.phone_number,
            "notifications_enabled": (user.metadata_json or {}).get("notifications_enabled", True),
            "two_factor_enabled": AuthService(session).is_two_factor_enabled(user),
        },
    )


@router.post("/change-password", response_model=PasswordResetResponse)
async def change_password(
    payload: ChangePasswordRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> PasswordResetResponse:
    return await AuthService(session).change_password(principal.user_id, payload.current_password, payload.new_password)


@router.delete("/profile", response_model=MessageResponse)
async def delete_profile(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    result = await AuthService(session).delete_profile(principal.user_id)
    return MessageResponse(message=result.message)


@router.get("/2fa/status", response_model=TwoFactorSetupResponse)
async def two_factor_status(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorSetupResponse:
    return await AuthService(session).get_two_factor_status(principal.user_id)


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_two_factor(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorSetupResponse:
    return await AuthService(session).initiate_two_factor_setup(principal.user_id)


@router.post("/2fa/enable", response_model=TwoFactorSetupResponse)
async def enable_two_factor(
    payload: TwoFactorCodeRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorSetupResponse:
    return await AuthService(session).enable_two_factor(principal.user_id, payload.code)


@router.post("/2fa/disable", response_model=TwoFactorSetupResponse)
async def disable_two_factor(
    payload: TwoFactorCodeRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorSetupResponse:
    return await AuthService(session).disable_two_factor(principal.user_id, payload.code)


@router.post("/2fa/verify", response_model=TokenPairResponse)
async def verify_two_factor(payload: TwoFactorVerifyRequest, session: AsyncSession = Depends(get_db_session)) -> TokenPairResponse:
    return await AuthService(session).verify_two_factor_login(payload.ticket, payload.code)
