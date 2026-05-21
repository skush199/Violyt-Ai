from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.integrations.object_storage import LocalObjectStorage
from app.services.asset_delivery import AssetDeliveryService


router = APIRouter()


@router.get("/download")
async def download_asset(token: str = Query(..., min_length=1)) -> FileResponse:
    delivery = AssetDeliveryService()
    storage = LocalObjectStorage()
    try:
        payload = delivery.verify_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        absolute_path = storage.absolute_path(str(payload["storage_path"]))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    path = Path(absolute_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")

    filename = str(payload.get("filename") or path.name)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    disposition = "attachment" if bool(payload.get("download")) else "inline"
    return FileResponse(
        absolute_path,
        media_type=media_type,
        filename=filename,
        content_disposition_type=disposition,
    )
