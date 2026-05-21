from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ChatMessage, ContentFolder, ContentSession, ContentVersion, GeneratedAsset
from app.repositories.base import Repository


class SessionRepository(Repository[ContentSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ContentSession)

    async def list_by_brand(
        self,
        brand_space_id: UUID,
        session_kind: str | None = None,
        tenant_id: UUID | None = None,
    ) -> list[ContentSession]:
        stmt = select(ContentSession).where(ContentSession.brand_space_id == brand_space_id)
        if tenant_id:
            stmt = stmt.where(ContentSession.tenant_id == tenant_id)
        stmt = stmt.order_by(ContentSession.updated_at.desc())
        if session_kind:
            stmt = stmt.where(ContentSession.session_kind == session_kind)
        result = await self.session.execute(
            stmt
        )
        return list(result.scalars().all())


class FolderRepository(Repository[ContentFolder]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ContentFolder)

    async def list_by_brand(self, brand_space_id: UUID, tenant_id: UUID | None = None) -> list[ContentFolder]:
        stmt = select(ContentFolder).where(ContentFolder.brand_space_id == brand_space_id)
        if tenant_id:
            stmt = stmt.where(ContentFolder.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_scoped(self, folder_id: UUID, tenant_id: UUID, brand_space_id: UUID | None = None) -> ContentFolder | None:
        stmt = select(ContentFolder).where(
            ContentFolder.id == folder_id,
            ContentFolder.tenant_id == tenant_id,
        )
        if brand_space_id:
            stmt = stmt.where(ContentFolder.brand_space_id == brand_space_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ContentRepository(Repository[ContentVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ContentVersion)

    async def list_by_brand(self, brand_space_id: UUID, tenant_id: UUID | None = None) -> list[ContentVersion]:
        stmt = select(ContentVersion).where(ContentVersion.brand_space_id == brand_space_id)
        if tenant_id:
            stmt = stmt.where(ContentVersion.tenant_id == tenant_id)
        stmt = stmt.order_by(ContentVersion.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_scoped(self, content_id: UUID, tenant_id: UUID, brand_space_id: UUID | None = None) -> ContentVersion | None:
        stmt = select(ContentVersion).where(
            ContentVersion.id == content_id,
            ContentVersion.tenant_id == tenant_id,
        )
        if brand_space_id:
            stmt = stmt.where(ContentVersion.brand_space_id == brand_space_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_session(
        self,
        session_id: UUID,
        tenant_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[ContentVersion]:
        stmt = select(ContentVersion).where(ContentVersion.session_id == session_id)
        if tenant_id:
            stmt = stmt.where(ContentVersion.tenant_id == tenant_id)
        stmt = stmt.order_by(ContentVersion.created_at.desc())
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AssetRepository(Repository[GeneratedAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GeneratedAsset)

    async def list_by_content(self, content_version_id: UUID) -> list[GeneratedAsset]:
        result = await self.session.execute(select(GeneratedAsset).where(GeneratedAsset.content_version_id == content_version_id))
        return list(result.scalars().all())

    async def get_scoped(self, asset_id: UUID, tenant_id: UUID, brand_space_id: UUID | None = None) -> GeneratedAsset | None:
        stmt = select(GeneratedAsset).where(
            GeneratedAsset.id == asset_id,
            GeneratedAsset.tenant_id == tenant_id,
        )
        if brand_space_id:
            stmt = stmt.where(GeneratedAsset.brand_space_id == brand_space_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_content_and_roles(self, content_version_id: UUID, roles: list[str]) -> list[GeneratedAsset]:
        result = await self.session.execute(
            select(GeneratedAsset).where(
                GeneratedAsset.content_version_id == content_version_id,
                GeneratedAsset.asset_role.in_(roles),
            )
        )
        return list(result.scalars().all())

    async def get_by_content_storage_role(
        self,
        content_version_id: UUID,
        storage_path: str,
        asset_role: str,
    ) -> GeneratedAsset | None:
        result = await self.session.execute(
            select(GeneratedAsset).where(
                GeneratedAsset.content_version_id == content_version_id,
                GeneratedAsset.storage_path == storage_path,
                GeneratedAsset.asset_role == asset_role,
            )
        )
        return result.scalar_one_or_none()


class ChatMessageRepository(Repository[ChatMessage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ChatMessage)

    async def list_by_session(self, session_id: UUID) -> list[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_recent_by_session(self, session_id: UUID, limit: int = 8) -> list[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(result.scalars().all())))
