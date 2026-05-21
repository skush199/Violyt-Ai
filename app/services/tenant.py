from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RoleCode
from app.core.exceptions import DuplicateResourceError, NotFoundError
from app.integrations.object_storage import LocalObjectStorage
from app.models.brand import BrandSpaceMember
from app.models.collaboration import UsageLimit
from app.models.content import ContentVersion, GeneratedAsset
from app.models.knowledge import KnowledgeAsset
from app.models.tenant import ActivationToken, Tenant, User, UserRole
from app.repositories.brand import BrandMemberRepository, BrandSpaceRepository
from app.repositories.collaboration import UsageLimitRepository
from app.repositories.tenant import ActivationTokenRepository, RoleRepository, TenantRepository, UserRepository, UserRoleRepository
from app.schemas.tenant import (
    TenantCreateRequest,
    TenantLogoUploadRequest,
    TenantUpdateRequest,
    TenantUsageLimitUpdate,
    TenantUserCreateRequest,
    TenantUserUpdateRequest,
)
from app.services.analytics import AnalyticsService
from app.services.email import EmailDeliveryResult, EmailService
from app.services.usage import UsageLimitService
from app.utils.files import decode_base64_content


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tenants = TenantRepository(session)
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.user_roles = UserRoleRepository(session)
        self.tokens = ActivationTokenRepository(session)
        self.usage_limits = UsageLimitRepository(session)
        self.brand_members = BrandMemberRepository(session)
        self.brand_spaces = BrandSpaceRepository(session)
        self.usage = UsageLimitService(session)
        self.analytics = AnalyticsService(session)
        self.storage = LocalObjectStorage()
        self.email = EmailService()

    async def _ensure_unique_tenant_slug(self, slug: str, *, current_tenant_id: UUID | None = None) -> None:
        existing = await self.tenants.get_by_slug(slug)
        if existing and existing.id != current_tenant_id:
            raise DuplicateResourceError(f"Tenant slug '{slug}' already exists. Use a different slug.")

    async def _ensure_unique_user_email(self, email: str, *, current_user_id: UUID | None = None) -> None:
        existing = await self.users.get_by_email(email)
        if existing and existing.id != current_user_id:
            raise DuplicateResourceError(f"A user with email '{email}' already exists.")

    async def create_tenant(self, payload: TenantCreateRequest) -> tuple[Tenant, EmailDeliveryResult]:
        await self._ensure_unique_tenant_slug(payload.slug)
        await self._ensure_unique_user_email(payload.admin_email)
        tenant = Tenant(
            name=payload.name,
            slug=payload.slug,
            contact_email=payload.contact_email,
            contact_number=payload.contact_number,
            address=payload.address,
            metadata_json=payload.metadata_json or {},
        )
        await self.tenants.add(tenant)
        admin = User(
            tenant_id=tenant.id,
            email=payload.admin_email,
            full_name=payload.admin_full_name,
            phone_number=payload.admin_phone_number,
            is_active=True,
            is_activated=False,
        )
        await self.users.add(admin)
        tenant_admin_role = await self.roles.get_by_code(RoleCode.TENANT_ADMIN)
        if not tenant_admin_role:
            raise NotFoundError("Tenant admin role not seeded")
        await self.user_roles.add(UserRole(user_id=admin.id, role_id=tenant_admin_role.id, brand_space_id=None))
        activation_token = str(uuid4())
        await self.tokens.add(
            ActivationToken(
                user_id=admin.id,
                token=activation_token,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
        await self.usage_limits.add(
            UsageLimit(
                tenant_id=tenant.id,
                max_users=payload.usage_limits.max_users,
                max_brand_spaces=payload.usage_limits.max_brand_spaces,
                max_content_generations=payload.usage_limits.max_content_generations,
                max_image_generations=payload.usage_limits.max_image_generations,
                max_ocr_pages=payload.usage_limits.max_ocr_pages,
            )
        )
        await self.usage.increment(tenant.id, "users", 1)
        await self.session.commit()
        await self.session.refresh(tenant)
        delivery = self.email.send_activation_email(admin.email, admin.full_name, activation_token)
        return tenant, delivery

    async def create_tenant_user(
        self,
        tenant_id: UUID,
        payload: TenantUserCreateRequest,
    ) -> tuple[User, EmailDeliveryResult]:
        await self._ensure_unique_user_email(payload.email)
        await self.usage.enforce(tenant_id, "users")
        role = await self.roles.get_by_code(payload.role_code)
        if not role:
            raise NotFoundError("Role not found")
        user = User(
            tenant_id=tenant_id,
            email=payload.email,
            full_name=payload.full_name,
            phone_number=payload.phone_number,
            is_active=True,
            is_activated=False,
        )
        await self.users.add(user)
        await self.user_roles.add(UserRole(user_id=user.id, role_id=role.id, brand_space_id=None))
        for brand_space_id in payload.brand_space_ids:
            await self.brand_members.add(
                __import__("app.models.brand", fromlist=["BrandSpaceMember"]).BrandSpaceMember(
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    user_id=user.id,
                    can_manage=False,
                )
            )
        activation_token = str(uuid4())
        await self.tokens.add(
            ActivationToken(
                user_id=user.id,
                token=activation_token,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
        await self.usage.increment(tenant_id, "users")
        await self.session.commit()
        await self.session.refresh(user)
        delivery = self.email.send_activation_email(user.email, user.full_name, activation_token)
        return user, delivery

    async def _get_primary_tenant_admin(self, tenant_id: UUID) -> User | None:
        users = await self.users.list_by_tenant(tenant_id)
        for user in users:
            roles = await self.user_roles.list_for_user(user.id)
            for item in roles:
                role = await self.roles.get(item.role_id)
                if role and role.code == RoleCode.TENANT_ADMIN:
                    return user
        return None

    async def list_users(self, tenant_id: UUID) -> list[User]:
        return await self.users.list_by_tenant(tenant_id)

    async def list_tenants(self) -> list[Tenant]:
        return await self.tenants.list()

    async def get_tenant(self, tenant_id: UUID) -> Tenant:
        tenant = await self.tenants.get(tenant_id)
        if not tenant:
            raise NotFoundError("Tenant not found")
        return tenant

    async def get_usage_summary(self, tenant_id: UUID) -> dict:
        usage_limit = await self.usage_limits.get_by_tenant(tenant_id)
        if not usage_limit:
            raise NotFoundError("Usage limit record not found")
        return {
            "tenant_id": tenant_id,
            "limits": {
                "max_users": usage_limit.max_users,
                "max_brand_spaces": usage_limit.max_brand_spaces,
                "max_content_generations": usage_limit.max_content_generations,
                "max_image_generations": usage_limit.max_image_generations,
                "max_ocr_pages": usage_limit.max_ocr_pages,
            },
            "consumption": await self.usage.summary(tenant_id),
        }

    async def get_tenant_summary(self, tenant_id: UUID) -> dict:
        tenant = await self.get_tenant(tenant_id)
        usage_summary = await self.get_usage_summary(tenant_id)
        metrics = await self.analytics.tenant_summary(tenant_id)
        admin_user = await self._get_primary_tenant_admin(tenant_id)
        last_login_result = await self.session.execute(
            select(func.max(User.last_login_at)).where(User.tenant_id == tenant_id)
        )
        last_login_at = last_login_result.scalar_one_or_none()
        active_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        last_active_at = last_login_at if last_login_at and last_login_at >= active_threshold else None
        token_usage = metrics.get("token_usage", {})
        return {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "contact_email": tenant.contact_email,
            "contact_number": tenant.contact_number,
            "address": tenant.address,
            "logo_asset_path": tenant.logo_asset_path,
            "is_active": tenant.is_active,
            "metadata_json": tenant.metadata_json or {},
            "created_at": tenant.created_at,
            "total_users": metrics["total_users"],
            "brand_space_count": metrics["number_of_brand_spaces"],
            "usage_limits": usage_summary["limits"],
            "usage_consumption": usage_summary["consumption"],
            "token_usage": {
                "input_tokens": int(token_usage.get("input_tokens") or 0),
                "output_tokens": int(token_usage.get("output_tokens") or 0),
                "total_tokens": int(token_usage.get("total_tokens") or 0),
            },
            "monthly_token_usage": token_usage.get("monthly_token_usage", []),
            "tenant_admin_name": admin_user.full_name if admin_user else None,
            "tenant_admin_email": admin_user.email if admin_user else None,
            "tenant_admin_phone_number": admin_user.phone_number if admin_user else None,
            "last_active_at": last_active_at,
        }

    async def list_tenant_brand_space_summaries(self, tenant_id: UUID) -> list[dict]:
        brands = await self.brand_spaces.list_by_tenant(tenant_id)
        active_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        summaries: list[dict] = []

        for brand in brands:
            content_generations = await self.session.scalar(
                select(func.count(ContentVersion.id)).where(
                    ContentVersion.tenant_id == tenant_id,
                    ContentVersion.brand_space_id == brand.id,
                )
            )
            visual_generations = await self.session.scalar(
                select(func.count(GeneratedAsset.id)).where(
                    GeneratedAsset.tenant_id == tenant_id,
                    GeneratedAsset.brand_space_id == brand.id,
                    GeneratedAsset.asset_role == "ai_image",
                )
            )
            ocr_pages = await self.session.scalar(
                select(func.coalesce(func.sum(KnowledgeAsset.page_count), 0)).where(
                    KnowledgeAsset.tenant_id == tenant_id,
                    KnowledgeAsset.brand_space_id == brand.id,
                )
            )
            last_login_at = await self.session.scalar(
                select(func.max(User.last_login_at))
                .select_from(BrandSpaceMember)
                .join(User, User.id == BrandSpaceMember.user_id)
                .where(
                    BrandSpaceMember.tenant_id == tenant_id,
                    BrandSpaceMember.brand_space_id == brand.id,
                )
            )
            last_active_at = last_login_at if last_login_at and last_login_at >= active_threshold else None

            summaries.append(
                {
                    "id": brand.id,
                    "tenant_id": brand.tenant_id,
                    "name": brand.name,
                    "slug": brand.slug,
                    "lifecycle_state": brand.lifecycle_state,
                    "created_at": brand.created_at,
                    "last_active_at": last_active_at,
                    "last_login_at": last_login_at,
                    "content_generations": content_generations or 0,
                    "visual_generations": visual_generations or 0,
                    "ocr_pages": int(ocr_pages or 0),
                }
            )

        return summaries

    async def build_user_summary(self, user: User) -> dict:
        roles = await self.user_roles.list_for_user(user.id)
        role_codes: list[str] = []
        brand_space_ids: list[UUID] = []
        for item in roles:
            role = await self.roles.get(item.role_id)
            if role:
                role_codes.append(role.code)
            if item.brand_space_id:
                brand_space_ids.append(item.brand_space_id)
        member_brand_ids = await self.brand_members.list_brand_ids_for_user(user.id)
        brand_space_ids.extend(item for item in member_brand_ids if item not in brand_space_ids)
        return {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "email": user.email,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "is_active": user.is_active,
            "is_activated": user.is_activated,
            "role_codes": sorted(set(role_codes)),
            "brand_space_ids": brand_space_ids,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
        }

    async def get_user_summary(self, tenant_id: UUID, user_id: UUID) -> dict:
        user = await self.users.get(user_id)
        if not user or user.tenant_id != tenant_id:
            raise NotFoundError("User not found")
        return await self.build_user_summary(user)

    async def deactivate_user(self, tenant_id: UUID, user_id: UUID) -> User:
        user = await self.users.get(user_id)
        if not user or user.tenant_id != tenant_id:
            raise NotFoundError("User not found")
        user.is_active = False
        await self.session.commit()
        return user

    async def update_tenant(self, tenant_id: UUID, payload: TenantUpdateRequest) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        if payload.slug is not None and payload.slug != tenant.slug:
            await self._ensure_unique_tenant_slug(payload.slug, current_tenant_id=tenant.id)
        if payload.name is not None:
            tenant.name = payload.name
        if payload.slug is not None:
            tenant.slug = payload.slug
        if payload.contact_email is not None:
            tenant.contact_email = payload.contact_email
        if payload.contact_number is not None:
            tenant.contact_number = payload.contact_number
        if payload.address is not None:
            tenant.address = payload.address
        if getattr(payload, "metadata_json", None) is not None:
            tenant.metadata_json = payload.metadata_json
        if payload.is_active is not None:
            tenant.is_active = payload.is_active

        admin_user = await self._get_primary_tenant_admin(tenant_id)
        if admin_user:
            if payload.admin_email is not None and payload.admin_email != admin_user.email:
                await self._ensure_unique_user_email(payload.admin_email, current_user_id=admin_user.id)
            if payload.admin_full_name is not None:
                admin_user.full_name = payload.admin_full_name
            if payload.admin_email is not None:
                admin_user.email = payload.admin_email
            if payload.admin_phone_number is not None:
                admin_user.phone_number = payload.admin_phone_number

        if payload.usage_limits is not None:
            await self.update_usage_limits(tenant_id, payload.usage_limits, auto_commit=False)

        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    async def upload_logo(self, tenant_id: UUID, payload: TenantLogoUploadRequest) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        content = decode_base64_content(payload.content_base64)
        if tenant.logo_asset_path:
            self.storage.delete(tenant.logo_asset_path)
        stored = self.storage.save_bytes(tenant.id, None, "tenant-assets", payload.filename, content)
        tenant.logo_asset_path = stored.storage_path
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    async def update_tenant_user(self, tenant_id: UUID, user_id: UUID, payload: TenantUserUpdateRequest) -> User:
        user = await self.users.get(user_id)
        if not user or user.tenant_id != tenant_id:
            raise NotFoundError("User not found")
        if payload.email is not None and payload.email != user.email:
            await self._ensure_unique_user_email(payload.email, current_user_id=user.id)
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.email is not None:
            user.email = payload.email
        if payload.phone_number is not None:
            user.phone_number = payload.phone_number
        if payload.is_active is not None:
            user.is_active = payload.is_active

        if payload.role_code is not None:
            role = await self.roles.get_by_code(payload.role_code)
            if not role:
                raise NotFoundError("Role not found")
            existing_roles = await self.user_roles.list_for_user(user.id)
            for item in existing_roles:
                await self.user_roles.delete(item)
            await self.user_roles.add(UserRole(user_id=user.id, role_id=role.id, brand_space_id=None))

        if payload.brand_space_ids is not None:
            existing_members = await self.brand_members.list_for_user(user.id, tenant_id)
            for member in existing_members:
                await self.brand_members.delete(member)
            for brand_space_id in payload.brand_space_ids:
                await self.brand_members.add(
                    __import__("app.models.brand", fromlist=["BrandSpaceMember"]).BrandSpaceMember(
                        tenant_id=tenant_id,
                        brand_space_id=brand_space_id,
                        user_id=user.id,
                        can_manage=False,
                    )
                )

        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_usage_limits(
        self,
        tenant_id: UUID,
        payload: TenantUsageLimitUpdate,
        *,
        auto_commit: bool = True,
    ) -> UsageLimit:
        usage_limit = await self.usage_limits.get_by_tenant(tenant_id)
        if not usage_limit:
            raise NotFoundError("Usage limit record not found")
        usage_limit.max_users = payload.max_users
        usage_limit.max_brand_spaces = payload.max_brand_spaces
        usage_limit.max_content_generations = payload.max_content_generations
        usage_limit.max_image_generations = payload.max_image_generations
        usage_limit.max_ocr_pages = payload.max_ocr_pages
        if auto_commit:
            await self.session.commit()
        return usage_limit
