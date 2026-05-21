from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeAsset, Template, TemplateMetadata
from app.repositories.base import Repository


class KnowledgeAssetRepository(Repository[KnowledgeAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, KnowledgeAsset)

    async def list_by_brand(self, brand_space_id: UUID, tenant_id: UUID | None = None) -> list[KnowledgeAsset]:
        stmt = select(KnowledgeAsset).where(KnowledgeAsset.brand_space_id == brand_space_id)
        if tenant_id:
            stmt = stmt.where(KnowledgeAsset.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_field(
        self,
        brand_space_id: UUID,
        field_key: str,
        tenant_id: UUID | None = None,
        active_only: bool = False,
    ) -> list[KnowledgeAsset]:
        stmt = select(KnowledgeAsset).where(
            KnowledgeAsset.brand_space_id == brand_space_id,
            KnowledgeAsset.field_key == field_key,
        )
        if tenant_id:
            stmt = stmt.where(KnowledgeAsset.tenant_id == tenant_id)
        if active_only:
            stmt = stmt.where(KnowledgeAsset.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_scoped(self, asset_id: UUID, tenant_id: UUID, brand_space_id: UUID | None = None) -> KnowledgeAsset | None:
        stmt = select(KnowledgeAsset).where(
            KnowledgeAsset.id == asset_id,
            KnowledgeAsset.tenant_id == tenant_id,
        )
        if brand_space_id:
            stmt = stmt.where(KnowledgeAsset.brand_space_id == brand_space_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class TemplateRepository(Repository[Template]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Template)

    async def list_by_brand(self, brand_space_id: UUID, tenant_id: UUID | None = None) -> list[Template]:
        stmt = select(Template).where(Template.brand_space_id == brand_space_id)
        if tenant_id:
            stmt = stmt.where(Template.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_scoped(self, template_id: UUID, tenant_id: UUID, brand_space_id: UUID | None = None) -> Template | None:
        stmt = select(Template).where(
            Template.id == template_id,
            Template.tenant_id == tenant_id,
        )
        if brand_space_id:
            stmt = stmt.where(Template.brand_space_id == brand_space_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_source_asset(self, source_asset_id: UUID) -> Template | None:
        result = await self.session.execute(
            select(Template).where(Template.source_knowledge_asset_id == source_asset_id)
        )
        return result.scalar_one_or_none()


class TemplateMetadataRepository(Repository[TemplateMetadata]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TemplateMetadata)

    async def get_by_template(self, template_id: UUID) -> TemplateMetadata | None:
        result = await self.session.execute(select(TemplateMetadata).where(TemplateMetadata.template_id == template_id))
        return result.scalar_one_or_none()
