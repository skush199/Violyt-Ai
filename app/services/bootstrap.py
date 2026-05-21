from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import RoleCode
from app.core.security import hash_password
from app.models.tenant import Permission, Role, RolePermission
from app.models.tenant import User, UserRole


DEFAULT_ROLES = [
    (RoleCode.SUPER_ADMIN, "Super Admin"),
    (RoleCode.TENANT_ADMIN, "Tenant Admin"),
    (RoleCode.TENANT_USER, "Tenant User"),
    (RoleCode.BRAND_USER, "Brand User"),
    (RoleCode.EXTERNAL_REVIEWER, "External Reviewer"),
]

DEFAULT_PERMISSIONS = [
    ("tenant.manage", "Manage tenants"),
    ("brand.manage", "Manage brand spaces"),
    ("content.generate", "Generate content"),
    ("knowledge.manage", "Manage knowledge"),
    ("analytics.view", "View analytics"),
    ("review.comment", "Comment on reviews"),
]

ROLE_PERMISSION_MAP = {
    RoleCode.SUPER_ADMIN: [code for code, _ in DEFAULT_PERMISSIONS],
    RoleCode.TENANT_ADMIN: ["brand.manage", "content.generate", "knowledge.manage", "analytics.view"],
    RoleCode.TENANT_USER: ["brand.manage", "content.generate", "knowledge.manage"],
    RoleCode.BRAND_USER: ["content.generate", "knowledge.manage"],
    RoleCode.EXTERNAL_REVIEWER: ["review.comment"],
}


async def seed_rbac(session: AsyncSession) -> None:
    for code, name in DEFAULT_ROLES:
        result = await session.execute(select(Role).where(Role.code == code))
        if not result.scalar_one_or_none():
            session.add(Role(code=code, name=name))
    for code, name in DEFAULT_PERMISSIONS:
        result = await session.execute(select(Permission).where(Permission.code == code))
        if not result.scalar_one_or_none():
            session.add(Permission(code=code, name=name))
    await session.commit()
    for role_code, permission_codes in ROLE_PERMISSION_MAP.items():
        role = (await session.execute(select(Role).where(Role.code == role_code))).scalar_one()
        for permission_code in permission_codes:
            permission = (await session.execute(select(Permission).where(Permission.code == permission_code))).scalar_one()
            existing = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission.id,
                )
            )
            if not existing.scalar_one_or_none():
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await session.commit()


async def seed_demo_owner(session: AsyncSession) -> None:
    settings = get_settings()
    if not settings.enable_demo_owner or settings.environment.lower() == "production":
        return

    role = (await session.execute(select(Role).where(Role.code == RoleCode.SUPER_ADMIN))).scalar_one_or_none()
    if not role:
        return

    user = (await session.execute(select(User).where(User.email == settings.demo_owner_email))).scalar_one_or_none()
    if not user:
        user = User(
            tenant_id=None,
            email=settings.demo_owner_email,
            full_name=settings.demo_owner_name,
            hashed_password=hash_password(settings.demo_owner_password),
            is_active=True,
            is_activated=True,
            metadata_json={"is_demo_owner": True},
        )
        session.add(user)
        await session.flush()
    else:
        user.full_name = settings.demo_owner_name
        user.hashed_password = hash_password(settings.demo_owner_password)
        user.is_active = True
        user.is_activated = True
        user.metadata_json = {
            **(user.metadata_json or {}),
            "is_demo_owner": True,
        }

    existing_role = await session.execute(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
            UserRole.brand_space_id.is_(None),
        )
    )
    if not existing_role.scalar_one_or_none():
        session.add(UserRole(user_id=user.id, role_id=role.id, brand_space_id=None))

    await session.commit()
