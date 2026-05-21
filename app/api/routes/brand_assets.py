from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, assert_brand_access, forbid_super_admin_brand_access, get_current_principal
from app.db.session import get_db_session
from app.schemas.brand_assets import (
    AssetCategoryRoutingResponse,
    AssetProcessingStatusResponse,
    AssetValidationResultResponse,
    BrandAttachmentListResponse,
    BrandAttachmentResponse,
    BrandAttachmentStatusUpdateResponse,
    BrandAttachmentUploadRequest,
    ReusableBrandAssetResponse,
)
from app.services.asset_delivery import AssetDeliveryService
from app.services.brand_assets import BrandAssetService


router = APIRouter()


def trust_level_for_validation_state(validation_state: str | None) -> str:
    normalized = str(validation_state or "pending").lower()
    if normalized == "clean":
        return "trusted"
    if normalized == "warning":
        return "usable_with_warning"
    if normalized == "excluded":
        return "excluded"
    return "reference_only"


async def serialize_attachment(service: BrandAssetService, asset) -> BrandAttachmentResponse:
    delivery = AssetDeliveryService()
    await service.session.refresh(asset)
    status = await service.processing_status.get_by_asset(asset.id)
    validation = next(
        (item for item in await service.validator.validation_results.list_by_asset_ids([asset.id]) if item.knowledge_asset_id == asset.id),
        None,
    )
    routing = await service.routing_repo.get_by_asset(asset.id)
    reusable_assets = await service.reusable_assets.list_by_knowledge_asset(asset.id)
    return BrandAttachmentResponse.model_validate(asset).model_copy(
        update={
            "asset_url": delivery.build_signed_url(
                storage_path=asset.storage_path,
                filename=asset.original_filename,
            ),
            "processing_status": AssetProcessingStatusResponse.model_validate(status) if status else None,
            "validation_result": AssetValidationResultResponse.model_validate(validation).model_copy(
                update={"trust_level": trust_level_for_validation_state(validation.validation_state)}
            )
            if validation
            else None,
            "routing": AssetCategoryRoutingResponse.model_validate(routing) if routing else None,
            "reusable_assets": [
                ReusableBrandAssetResponse.model_validate(reusable_asset).model_copy(
                    update={
                        "asset_url": delivery.build_signed_url(
                            storage_path=reusable_asset.storage_path,
                            filename=reusable_asset.label or reusable_asset.storage_path.rsplit("/", 1)[-1],
                        ),
                        "review_class": (reusable_asset.normalized_metadata_json or {}).get("review_class"),
                        "review_status": (reusable_asset.normalized_metadata_json or {}).get("review_status"),
                        "review_reason": (reusable_asset.normalized_metadata_json or {}).get("review_reason"),
                    }
                )
                for reusable_asset in reusable_assets
            ],
        }
    )


@router.post("/{brand_id}/attachments/{field_key}", response_model=BrandAttachmentResponse)
async def upload_brand_attachment(
    brand_id: UUID,
    field_key: str,
    payload: BrandAttachmentUploadRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BrandAttachmentResponse:
    forbid_super_admin_brand_access(principal)
    assert_brand_access(principal, brand_id)
    service = BrandAssetService(session)
    asset = await service.upload(principal.tenant_id, brand_id, field_key, payload)
    return await serialize_attachment(service, asset)


@router.get("/{brand_id}/attachments", response_model=list[BrandAttachmentListResponse])
async def list_brand_attachments(
    brand_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[BrandAttachmentListResponse]:
    forbid_super_admin_brand_access(principal)
    assert_brand_access(principal, brand_id)
    service = BrandAssetService(session)
    assets = await service.list(principal.tenant_id, brand_id)
    grouped: dict[str, list] = {}
    for asset in assets:
        grouped.setdefault(asset.field_key or "uncategorized", []).append(asset)
    responses: list[BrandAttachmentListResponse] = []
    for field_key, items in grouped.items():
        responses.append(
            BrandAttachmentListResponse(
                field_key=field_key,
                assets=[await serialize_attachment(service, item) for item in items],
            )
        )
    return responses


@router.get("/{brand_id}/attachments/fields/{field_key}", response_model=BrandAttachmentListResponse)
async def list_brand_attachments_by_field(
    brand_id: UUID,
    field_key: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BrandAttachmentListResponse:
    forbid_super_admin_brand_access(principal)
    assert_brand_access(principal, brand_id)
    service = BrandAssetService(session)
    assets = await service.list(principal.tenant_id, brand_id, field_key=field_key)
    return BrandAttachmentListResponse(
        field_key=field_key,
        assets=[await serialize_attachment(service, asset) for asset in assets],
    )


@router.get("/{brand_id}/attachments/assets/{asset_id}", response_model=BrandAttachmentResponse)
async def get_brand_attachment(
    brand_id: UUID,
    asset_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BrandAttachmentResponse:
    forbid_super_admin_brand_access(principal)
    assert_brand_access(principal, brand_id)
    service = BrandAssetService(session)
    asset = await service.get_scoped(principal.tenant_id, brand_id, asset_id)
    return await serialize_attachment(service, asset)


@router.post("/{brand_id}/attachments/assets/{asset_id}/reprocess", response_model=BrandAttachmentStatusUpdateResponse)
async def reprocess_brand_attachment(
    brand_id: UUID,
    asset_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BrandAttachmentStatusUpdateResponse:
    forbid_super_admin_brand_access(principal)
    assert_brand_access(principal, brand_id)
    service = BrandAssetService(session)
    asset = await service.reprocess(principal.tenant_id, brand_id, asset_id)
    return BrandAttachmentStatusUpdateResponse(
        asset=await serialize_attachment(service, asset),
        message="Attachment queued for reprocessing.",
    )


@router.post("/{brand_id}/attachments/assets/{asset_id}/unsync", response_model=BrandAttachmentStatusUpdateResponse)
async def unsync_brand_attachment(
    brand_id: UUID,
    asset_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BrandAttachmentStatusUpdateResponse:
    forbid_super_admin_brand_access(principal)
    assert_brand_access(principal, brand_id)
    service = BrandAssetService(session)
    asset = await service.unsync(principal.tenant_id, brand_id, asset_id)
    return BrandAttachmentStatusUpdateResponse(
        asset=await serialize_attachment(service, asset),
        message="Attachment unsynced from the active brand context.",
    )


@router.delete("/{brand_id}/attachments/assets/{asset_id}", response_model=BrandAttachmentStatusUpdateResponse)
async def delete_brand_attachment(
    brand_id: UUID,
    asset_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BrandAttachmentStatusUpdateResponse:
    forbid_super_admin_brand_access(principal)
    assert_brand_access(principal, brand_id)
    service = BrandAssetService(session)
    asset = await service.delete(principal.tenant_id, brand_id, asset_id)
    return BrandAttachmentStatusUpdateResponse(
        asset=await serialize_attachment(service, asset),
        message="Attachment deleted.",
    )
