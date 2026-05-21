from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.brand_intelligence import BrandIntelligenceService
from app.core.enums import BrandSpaceLifecycle, RoleCode, UsageMetricCode
from app.core.exceptions import LifecycleError, NotFoundError
from app.models.brand import BrandConfigurationSection, BrandSpace, BrandSpaceMember, Guardrail, Objective, Persona
from app.repositories.brand import (
    BrandMemberRepository,
    BrandSectionRepository,
    BrandSpaceRepository,
    GuardrailRepository,
    ObjectiveRepository,
    PersonaRepository,
)
from app.schemas.brand import BrandCreateRequest, BrandSectionUpsertRequest, BrandUpdateRequest, GuardrailPayload
from app.services.data_validation import DataValidatorService
from app.services.usage import UsageLimitService
from app.utils.text import slugify


class BrandSpaceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.brands = BrandSpaceRepository(session)
        self.sections = BrandSectionRepository(session)
        self.personas = PersonaRepository(session)
        self.guardrails = GuardrailRepository(session)
        self.objectives = ObjectiveRepository(session)
        self.members = BrandMemberRepository(session)
        self.usage = UsageLimitService(session)
        self.intelligence = BrandIntelligenceService()
        self.validator = DataValidatorService(session)

    async def _commit_and_refresh_brand(self, brand: BrandSpace) -> BrandSpace:
        await self.session.commit()
        await self.session.refresh(brand)
        return brand

    @staticmethod
    def _build_guardrail_record(payload: dict) -> dict:
        # Guardrail sections may include asset references and other section-only
        # metadata. The relational guardrails table stores only the core rule set.
        return GuardrailPayload.model_validate(payload).model_dump(
            exclude={
                "positive_word_bank_asset_ids",
                "negative_word_bank_asset_ids",
                "replaceable_word_bank_asset_ids",
            }
        )

    async def create_brand(self, tenant_id: UUID, created_by: UUID, payload: BrandCreateRequest) -> BrandSpace:
        await self.usage.enforce(tenant_id, UsageMetricCode.BRAND_SPACES)
        slug = slugify(payload.identity.brand_name)
        brand = BrandSpace(
            tenant_id=tenant_id,
            name=payload.identity.brand_name,
            slug=slug,
            description=payload.identity.brand_description,
            industry_category=payload.identity.industry_category,
            sub_industry=payload.identity.sub_industry,
            geography_country=payload.identity.target_geography.get("country"),
            geography_city=payload.identity.target_geography.get("city"),
            audience_type=payload.identity.audience_type,
            lifecycle_state=BrandSpaceLifecycle.DRAFT,
            overview_snapshot={},
            resolved_brand_context={},
        )
        await self.brands.add(brand)
        await self.members.add(
            BrandSpaceMember(
                tenant_id=tenant_id,
                brand_space_id=brand.id,
                user_id=created_by,
                can_manage=True,
            )
        )
        await self.sections.add(
            BrandConfigurationSection(
                tenant_id=tenant_id,
                brand_space_id=brand.id,
                section_code="identity",
                payload=payload.identity.model_dump(),
                completion_percent=100,
            )
        )
        if payload.foundations:
            await self.sections.add(
                BrandConfigurationSection(
                    tenant_id=tenant_id,
                    brand_space_id=brand.id,
                    section_code="foundations",
                    payload=payload.foundations.model_dump(),
                    completion_percent=100,
                )
            )
        else:
            await self.sections.add(
                BrandConfigurationSection(
                    tenant_id=tenant_id,
                    brand_space_id=brand.id,
                    section_code="foundations",
                    payload={},
                    completion_percent=0,
                )
            )
        if payload.voice_tone:
            await self.sections.add(
                BrandConfigurationSection(
                    tenant_id=tenant_id,
                    brand_space_id=brand.id,
                    section_code="voice_tone",
                    payload=payload.voice_tone.model_dump(),
                    completion_percent=100,
                )
            )
        else:
            await self.sections.add(
                BrandConfigurationSection(
                    tenant_id=tenant_id,
                    brand_space_id=brand.id,
                    section_code="voice_tone",
                    payload={},
                    completion_percent=0,
                )
            )
        for section_code in ["personas", "guardrails", "knowledge", "objectives", "visual_identity", "prompt_intelligence", "review"]:
            await self.sections.add(
                BrandConfigurationSection(
                    tenant_id=tenant_id,
                    brand_space_id=brand.id,
                    section_code=section_code,
                    payload={},
                    completion_percent=0,
                )
            )
        await self.usage.increment(tenant_id, UsageMetricCode.BRAND_SPACES)
        await self.session.commit()
        return await self.refresh_context(brand.id)

    async def refresh_context(self, brand_space_id: UUID) -> BrandSpace:
        brand, _snapshot = await self.validator.refresh_brand_context(brand_space_id)
        return brand

    async def upsert_section(self, tenant_id: UUID, brand_space_id: UUID, payload: BrandSectionUpsertRequest) -> BrandSpace:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        existing_sections = await self.sections.list_current_sections(brand_space_id, tenant_id)
        for existing in existing_sections:
            if existing.section_code == payload.section_code:
                existing.is_current = False
        await self.sections.add(
            BrandConfigurationSection(
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                section_code=payload.section_code,
                version=max([s.version for s in existing_sections if s.section_code == payload.section_code], default=0) + 1,
                is_current=True,
                completion_percent=payload.completion_percent,
                payload=payload.payload,
            )
        )

        if payload.section_code == "identity":
            brand.name = payload.payload.get("brand_name", brand.name)
            brand.description = payload.payload.get("brand_description", brand.description)
            brand.industry_category = payload.payload.get("industry_category")
            brand.sub_industry = payload.payload.get("sub_industry")
            target_geography = payload.payload.get("target_geography", {}) or {}
            brand.geography_country = target_geography.get("country")
            brand.geography_city = target_geography.get("city")
            brand.audience_type = payload.payload.get("audience_type")
        if payload.section_code == "foundations":
            brand.overview_snapshot = {
                **brand.overview_snapshot,
                "foundations": payload.payload,
            }
        if payload.section_code == "voice_tone":
            brand.overview_snapshot = {
                **brand.overview_snapshot,
                "voice_tone": payload.payload,
            }
        if payload.section_code == "visual_identity":
            brand.overview_snapshot = {
                **brand.overview_snapshot,
                "visual_identity": payload.payload,
            }

        if payload.section_code == "personas":
            existing_personas = await self.personas.list_by_brand(brand_space_id, tenant_id)
            for existing in existing_personas:
                await self.personas.delete(existing)
            default_persona_id = None
            for item in payload.payload.get("personas", []):
                created = await self.personas.add(Persona(tenant_id=tenant_id, brand_space_id=brand_space_id, **item))
                if created.is_default:
                    default_persona_id = created.id
            brand.default_persona_id = default_persona_id
        if payload.section_code == "guardrails":
            existing_guardrails = await self.guardrails.list_by_brand(brand_space_id, tenant_id)
            for existing in existing_guardrails:
                await self.guardrails.delete(existing)
            await self.guardrails.add(
                Guardrail(
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    **self._build_guardrail_record(payload.payload),
                )
            )
        if payload.section_code == "objectives":
            existing_objectives = await self.objectives.list_by_brand(brand_space_id, tenant_id)
            for existing in existing_objectives:
                await self.objectives.delete(existing)
            for item in payload.payload.get("objectives", []):
                await self.objectives.add(Objective(tenant_id=tenant_id, brand_space_id=brand_space_id, **item))
        await self.session.commit()
        return await self.refresh_context(brand_space_id)

    async def update_brand(self, tenant_id: UUID, brand_space_id: UUID, payload: BrandUpdateRequest) -> BrandSpace:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        if payload.description is not None:
            brand.description = payload.description
        if payload.overview_snapshot is not None:
            brand.overview_snapshot = payload.overview_snapshot
        return await self._commit_and_refresh_brand(brand)

    async def finalize_brand(self, tenant_id: UUID, brand_space_id: UUID) -> BrandSpace:
        return await self.publish_brand(tenant_id, brand_space_id)

    async def publish_brand(self, tenant_id: UUID, brand_space_id: UUID) -> BrandSpace:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        sections = await self.sections.list_current_sections(brand_space_id, tenant_id)
        identity_section = next((section for section in sections if section.section_code == "identity"), None)
        if not identity_section or not identity_section.payload.get("brand_name"):
            raise LifecycleError("Brand Space cannot be published without a brand identity.")
        brand = await self.refresh_context(brand_space_id)
        brand.lifecycle_state = BrandSpaceLifecycle.ACTIVE
        brand.is_finalized = True
        return await self._commit_and_refresh_brand(brand)

    async def unpublish_brand(self, tenant_id: UUID, brand_space_id: UUID) -> BrandSpace:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        brand.lifecycle_state = BrandSpaceLifecycle.DRAFT
        return await self._commit_and_refresh_brand(brand)

    async def archive_brand(self, tenant_id: UUID, brand_space_id: UUID) -> BrandSpace:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        brand.lifecycle_state = BrandSpaceLifecycle.ARCHIVED
        return await self._commit_and_refresh_brand(brand)

    async def restore_brand(self, tenant_id: UUID, brand_space_id: UUID) -> BrandSpace:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        brand.lifecycle_state = BrandSpaceLifecycle.ACTIVE
        return await self._commit_and_refresh_brand(brand)

    async def delete_brand(self, tenant_id: UUID, brand_space_id: UUID) -> BrandSpace:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        brand.lifecycle_state = BrandSpaceLifecycle.DELETED
        return await self._commit_and_refresh_brand(brand)

    async def list_brands(self, tenant_id: UUID, user_id: UUID, role_codes: set[str]) -> list[BrandSpace]:
        if RoleCode.BRAND_USER in role_codes:
            brand_ids = await self.members.list_brand_ids_for_user(user_id)
            all_brands = await self.brands.list_by_tenant(tenant_id)
            return [brand for brand in all_brands if brand.id in set(brand_ids)]
        return await self.brands.list_by_tenant(tenant_id)

    async def require_active(self, tenant_id: UUID, brand_space_id: UUID) -> BrandSpace:
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        if brand.lifecycle_state != BrandSpaceLifecycle.ACTIVE:
            raise LifecycleError("Brand Space must be Active")
        return brand
