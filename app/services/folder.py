from __future__ import annotations

from uuid import UUID

from app.core.exceptions import NotFoundError
from app.models.content import ContentFolder
from app.repositories.content import ContentRepository, FolderRepository
from sqlalchemy.ext.asyncio import AsyncSession


class FolderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.folders = FolderRepository(session)
        self.contents = ContentRepository(session)

    async def create(self, tenant_id: UUID, brand_space_id: UUID, created_by: UUID, name: str, description: str | None = None) -> ContentFolder:
        folder = ContentFolder(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            name=name,
            description=description,
            created_by=created_by,
        )
        await self.folders.add(folder)
        await self.session.commit()
        return folder

    async def rename(self, folder_id: UUID, name: str) -> ContentFolder:
        folder = await self.folders.get(folder_id)
        if not folder:
            raise NotFoundError("Folder not found")
        folder.name = name
        await self.session.commit()
        return folder

    async def rename_scoped(self, tenant_id: UUID, brand_space_id: UUID, folder_id: UUID, name: str) -> ContentFolder:
        folder = await self.folders.get_scoped(folder_id, tenant_id, brand_space_id)
        if not folder:
            raise NotFoundError("Folder not found")
        folder.name = name
        await self.session.commit()
        return folder

    async def delete(self, folder_id: UUID) -> None:
        folder = await self.folders.get(folder_id)
        if not folder:
            raise NotFoundError("Folder not found")
        await self.folders.delete(folder)
        await self.session.commit()

    async def delete_scoped(self, tenant_id: UUID, brand_space_id: UUID, folder_id: UUID) -> None:
        folder = await self.folders.get_scoped(folder_id, tenant_id, brand_space_id)
        if not folder:
            raise NotFoundError("Folder not found")
        await self.folders.delete(folder)
        await self.session.commit()

    async def move_content(self, content_version_id: UUID, folder_id: UUID) -> None:
        content = await self.contents.get(content_version_id)
        folder = await self.folders.get(folder_id)
        if not content or not folder:
            raise NotFoundError("Content or folder not found")
        content.folder_id = folder_id
        content.lifecycle_state = "organized"
        await self.session.commit()

    async def move_content_scoped(self, tenant_id: UUID, brand_space_id: UUID, content_version_id: UUID, folder_id: UUID) -> None:
        content = await self.contents.get_scoped(content_version_id, tenant_id, brand_space_id)
        folder = await self.folders.get_scoped(folder_id, tenant_id, brand_space_id)
        if not content or not folder:
            raise NotFoundError("Content or folder not found")
        content.folder_id = folder_id
        content.lifecycle_state = "organized"
        await self.session.commit()

    async def list(self, tenant_id: UUID, brand_space_id: UUID) -> list[ContentFolder]:
        return await self.folders.list_by_brand(brand_space_id, tenant_id)
