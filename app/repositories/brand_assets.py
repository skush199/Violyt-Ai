from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_assets import (
    AssetCategoryRouting,
    AssetProcessingStatus,
    AssetValidationResult,
    AudienceInsightAsset,
    AudienceInsightStructuredData,
    BrandCTATemplate,
    BrandLegalAsset,
    BrandLogoAsset,
    BrandLogoMetadata,
    ColorPaletteEntry,
    DataConflict,
    MoodBoardAsset,
    NegativeWord,
    PositiveWord,
    ReplaceableWord,
    ReusableBrandAsset,
    ResolvedBrandContextSnapshot,
    TypographyGuide,
    VisualReferenceAsset,
    WordBankUpload,
)
from app.repositories.base import Repository


ModelT = TypeVar("ModelT")


class ScopedRepository(Repository[ModelT]):
    async def get_for_brand(self, entity_id: UUID, tenant_id: UUID, brand_space_id: UUID) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.id == entity_id,
                self.model.tenant_id == tenant_id,
                self.model.brand_space_id == brand_space_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_brand(self, tenant_id: UUID, brand_space_id: UUID) -> list[ModelT]:
        result = await self.session.execute(
            select(self.model).where(
                self.model.tenant_id == tenant_id,
                self.model.brand_space_id == brand_space_id,
            )
        )
        return list(result.scalars().all())


class BrandLogoAssetRepository(ScopedRepository[BrandLogoAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BrandLogoAsset)

    async def get_by_knowledge_asset(self, knowledge_asset_id: UUID) -> BrandLogoAsset | None:
        result = await self.session.execute(
            select(BrandLogoAsset).where(BrandLogoAsset.knowledge_asset_id == knowledge_asset_id)
        )
        return result.scalar_one_or_none()


class BrandLogoMetadataRepository(ScopedRepository[BrandLogoMetadata]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BrandLogoMetadata)

    async def get_by_logo_asset(self, brand_logo_asset_id: UUID) -> BrandLogoMetadata | None:
        result = await self.session.execute(
            select(BrandLogoMetadata).where(BrandLogoMetadata.brand_logo_asset_id == brand_logo_asset_id)
        )
        return result.scalar_one_or_none()


class AudienceInsightAssetRepository(ScopedRepository[AudienceInsightAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AudienceInsightAsset)

    async def get_by_knowledge_asset(self, knowledge_asset_id: UUID) -> AudienceInsightAsset | None:
        result = await self.session.execute(
            select(AudienceInsightAsset).where(AudienceInsightAsset.knowledge_asset_id == knowledge_asset_id)
        )
        return result.scalar_one_or_none()


class AudienceInsightStructuredDataRepository(ScopedRepository[AudienceInsightStructuredData]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AudienceInsightStructuredData)

    async def get_by_audience_asset(self, audience_asset_id: UUID) -> AudienceInsightStructuredData | None:
        result = await self.session.execute(
            select(AudienceInsightStructuredData).where(
                AudienceInsightStructuredData.audience_insight_asset_id == audience_asset_id
            )
        )
        return result.scalar_one_or_none()


class VisualReferenceAssetRepository(ScopedRepository[VisualReferenceAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VisualReferenceAsset)

    async def get_by_knowledge_asset(self, knowledge_asset_id: UUID) -> VisualReferenceAsset | None:
        result = await self.session.execute(
            select(VisualReferenceAsset).where(VisualReferenceAsset.knowledge_asset_id == knowledge_asset_id)
        )
        return result.scalar_one_or_none()


class MoodBoardAssetRepository(ScopedRepository[MoodBoardAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MoodBoardAsset)

    async def get_by_knowledge_asset(self, knowledge_asset_id: UUID) -> MoodBoardAsset | None:
        result = await self.session.execute(
            select(MoodBoardAsset).where(MoodBoardAsset.knowledge_asset_id == knowledge_asset_id)
        )
        return result.scalar_one_or_none()


class ReusableBrandAssetRepository(ScopedRepository[ReusableBrandAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ReusableBrandAsset)

    async def list_by_brand(
        self,
        brand_space_id: UUID,
        *,
        tenant_id: UUID | None = None,
        active_only: bool = True,
    ) -> list[ReusableBrandAsset]:
        query = select(ReusableBrandAsset).where(ReusableBrandAsset.brand_space_id == brand_space_id)
        if tenant_id is not None:
            query = query.where(ReusableBrandAsset.tenant_id == tenant_id)
        if active_only:
            query = query.where(ReusableBrandAsset.is_active.is_(True))
        result = await self.session.execute(query.order_by(ReusableBrandAsset.created_at.desc()))
        return list(result.scalars().all())

    async def list_by_knowledge_asset(self, knowledge_asset_id: UUID) -> list[ReusableBrandAsset]:
        result = await self.session.execute(
            select(ReusableBrandAsset).where(ReusableBrandAsset.knowledge_asset_id == knowledge_asset_id)
        )
        return list(result.scalars().all())

    async def delete_by_knowledge_asset(self, knowledge_asset_id: UUID) -> None:
        await self.session.execute(
            delete(ReusableBrandAsset).where(ReusableBrandAsset.knowledge_asset_id == knowledge_asset_id)
        )
        await self.session.flush()


class ColorPaletteEntryRepository(ScopedRepository[ColorPaletteEntry]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ColorPaletteEntry)

    async def delete_by_asset(self, knowledge_asset_id: UUID) -> None:
        await self.session.execute(delete(ColorPaletteEntry).where(ColorPaletteEntry.knowledge_asset_id == knowledge_asset_id))
        await self.session.flush()


class TypographyGuideRepository(ScopedRepository[TypographyGuide]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TypographyGuide)

    async def get_by_knowledge_asset(self, knowledge_asset_id: UUID) -> TypographyGuide | None:
        result = await self.session.execute(
            select(TypographyGuide).where(TypographyGuide.knowledge_asset_id == knowledge_asset_id)
        )
        return result.scalar_one_or_none()


class WordBankUploadRepository(ScopedRepository[WordBankUpload]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WordBankUpload)

    async def get_by_knowledge_asset(self, knowledge_asset_id: UUID) -> WordBankUpload | None:
        result = await self.session.execute(
            select(WordBankUpload).where(WordBankUpload.knowledge_asset_id == knowledge_asset_id)
        )
        return result.scalar_one_or_none()


class PositiveWordRepository(ScopedRepository[PositiveWord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PositiveWord)

    async def delete_by_upload(self, upload_id: UUID) -> None:
        await self.session.execute(delete(PositiveWord).where(PositiveWord.upload_id == upload_id))
        await self.session.flush()


class NegativeWordRepository(ScopedRepository[NegativeWord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NegativeWord)

    async def delete_by_upload(self, upload_id: UUID) -> None:
        await self.session.execute(delete(NegativeWord).where(NegativeWord.upload_id == upload_id))
        await self.session.flush()


class ReplaceableWordRepository(ScopedRepository[ReplaceableWord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ReplaceableWord)

    async def delete_by_upload(self, upload_id: UUID) -> None:
        await self.session.execute(delete(ReplaceableWord).where(ReplaceableWord.upload_id == upload_id))
        await self.session.flush()


class AssetProcessingStatusRepository(ScopedRepository[AssetProcessingStatus]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AssetProcessingStatus)

    async def get_by_asset(self, knowledge_asset_id: UUID) -> AssetProcessingStatus | None:
        result = await self.session.execute(
            select(AssetProcessingStatus).where(AssetProcessingStatus.knowledge_asset_id == knowledge_asset_id)
        )
        return result.scalar_one_or_none()


class AssetValidationResultRepository(ScopedRepository[AssetValidationResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AssetValidationResult)

    async def list_by_asset_ids(self, asset_ids: list[UUID]) -> list[AssetValidationResult]:
        if not asset_ids:
            return []
        result = await self.session.execute(
            select(AssetValidationResult).where(AssetValidationResult.knowledge_asset_id.in_(asset_ids))
        )
        return list(result.scalars().all())


class AssetCategoryRoutingRepository(ScopedRepository[AssetCategoryRouting]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AssetCategoryRouting)

    async def get_by_asset(self, knowledge_asset_id: UUID) -> AssetCategoryRouting | None:
        result = await self.session.execute(
            select(AssetCategoryRouting).where(AssetCategoryRouting.knowledge_asset_id == knowledge_asset_id)
        )
        return result.scalar_one_or_none()


class DataConflictRepository(ScopedRepository[DataConflict]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DataConflict)

    async def delete_open_for_brand(self, tenant_id: UUID, brand_space_id: UUID) -> None:
        await self.session.execute(
            delete(DataConflict).where(
                DataConflict.tenant_id == tenant_id,
                DataConflict.brand_space_id == brand_space_id,
                DataConflict.resolution_status == "open",
            )
        )
        await self.session.flush()


class ResolvedBrandContextSnapshotRepository(ScopedRepository[ResolvedBrandContextSnapshot]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ResolvedBrandContextSnapshot)

    async def latest_for_brand(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        snapshot_kind: str = "validated",
    ) -> ResolvedBrandContextSnapshot | None:
        result = await self.session.execute(
            select(ResolvedBrandContextSnapshot)
            .where(
                ResolvedBrandContextSnapshot.tenant_id == tenant_id,
                ResolvedBrandContextSnapshot.brand_space_id == brand_space_id,
                ResolvedBrandContextSnapshot.snapshot_kind == snapshot_kind,
            )
            .order_by(ResolvedBrandContextSnapshot.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def trim_for_brand(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        *,
        snapshot_kind: str = "validated",
        keep_latest: int = 25,
    ) -> None:
        if keep_latest <= 0:
            await self.session.execute(
                delete(ResolvedBrandContextSnapshot).where(
                    ResolvedBrandContextSnapshot.tenant_id == tenant_id,
                    ResolvedBrandContextSnapshot.brand_space_id == brand_space_id,
                    ResolvedBrandContextSnapshot.snapshot_kind == snapshot_kind,
                )
            )
            await self.session.flush()
            return
        result = await self.session.execute(
            select(ResolvedBrandContextSnapshot.id)
            .where(
                ResolvedBrandContextSnapshot.tenant_id == tenant_id,
                ResolvedBrandContextSnapshot.brand_space_id == brand_space_id,
                ResolvedBrandContextSnapshot.snapshot_kind == snapshot_kind,
            )
            .order_by(ResolvedBrandContextSnapshot.created_at.desc())
            .offset(keep_latest)
        )
        stale_ids = [row[0] for row in result.all()]
        if not stale_ids:
            return
        await self.session.execute(
            delete(ResolvedBrandContextSnapshot).where(ResolvedBrandContextSnapshot.id.in_(stale_ids))
        )
        await self.session.flush()


class BrandLegalAssetRepository(ScopedRepository[BrandLegalAsset]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BrandLegalAsset)

    async def get_by_brand_space(self, brand_space_id: UUID) -> list[BrandLegalAsset]:
        result = await self.session.execute(
            select(BrandLegalAsset).where(BrandLegalAsset.brand_space_id == brand_space_id)
        )
        return list(result.scalars().all())

    async def get_by_source_asset(self, source_asset_id: UUID) -> BrandLegalAsset | None:
        result = await self.session.execute(
            select(BrandLegalAsset).where(BrandLegalAsset.source_asset_id == source_asset_id)
        )
        return result.scalar_one_or_none()


class BrandCTATemplateRepository(ScopedRepository[BrandCTATemplate]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BrandCTATemplate)

    async def get_by_brand_space(self, brand_space_id: UUID) -> list[BrandCTATemplate]:
        result = await self.session.execute(
            select(BrandCTATemplate).where(BrandCTATemplate.brand_space_id == brand_space_id)
        )
        return list(result.scalars().all())

    async def get_default(self, brand_space_id: UUID) -> BrandCTATemplate | None:
        result = await self.session.execute(
            select(BrandCTATemplate).where(
                BrandCTATemplate.brand_space_id == brand_space_id,
                BrandCTATemplate.is_default == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()
