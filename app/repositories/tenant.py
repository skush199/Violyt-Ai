from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import ActivationToken, Permission, Role, Tenant, User, UserRole
from app.repositories.base import Repository


class TenantRepository(Repository[Tenant]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Tenant)

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()


class UserRepository(Repository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: UUID) -> list[User]:
        result = await self.session.execute(select(User).where(User.tenant_id == tenant_id))
        return list(result.scalars().all())


class RoleRepository(Repository[Role]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Role)

    async def get_by_code(self, code: str) -> Role | None:
        result = await self.session.execute(select(Role).where(Role.code == code))
        return result.scalar_one_or_none()


class UserRoleRepository(Repository[UserRole]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserRole)

    async def list_for_user(self, user_id: UUID) -> list[UserRole]:
        result = await self.session.execute(select(UserRole).where(UserRole.user_id == user_id))
        return list(result.scalars().all())

    async def list_for_user_in_tenant(self, user_id: UUID, brand_space_ids: list[UUID] | None = None) -> list[UserRole]:
        stmt = select(UserRole).where(UserRole.user_id == user_id)
        if brand_space_ids is not None:
            stmt = stmt.where((UserRole.brand_space_id.is_(None)) | (UserRole.brand_space_id.in_(brand_space_ids)))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ActivationTokenRepository(Repository[ActivationToken]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ActivationToken)

    async def get_by_token(self, token: str) -> ActivationToken | None:
        result = await self.session.execute(select(ActivationToken).where(ActivationToken.token == token))
        return result.scalar_one_or_none()


class PermissionRepository(Repository[Permission]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Permission)
