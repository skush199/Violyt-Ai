from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import NotFoundError
from app.models.collaboration import SocialConnection
from app.repositories.content import AssetRepository, ContentRepository
from app.repositories.collaboration import SocialConnectionRepository


class SocialService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.connections = SocialConnectionRepository(session)
        self.contents = ContentRepository(session)
        self.assets = AssetRepository(session)

    async def list_connections(self, tenant_id: UUID, brand_space_id: UUID) -> list[SocialConnection]:
        return await self.connections.list_by_brand(tenant_id, brand_space_id)

    async def connect(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        platform: str,
        account_name: str | None,
        account_identifier: str | None,
        access_token: str | None,
        refresh_token: str | None,
        scopes: list[str],
    ) -> SocialConnection:
        connection = await self.connections.get_by_platform(brand_space_id, platform)
        if not connection:
            connection = SocialConnection(
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                platform=platform,
                account_name=account_name,
                account_identifier=account_identifier,
                access_token_encrypted=encrypt_secret(access_token),
                refresh_token_encrypted=encrypt_secret(refresh_token),
                scopes=scopes,
                is_connected=True,
            )
            await self.connections.add(connection)
        else:
            connection.account_name = account_name
            connection.account_identifier = account_identifier
            if access_token is not None:
                connection.access_token_encrypted = encrypt_secret(access_token)
            if refresh_token is not None:
                connection.refresh_token_encrypted = encrypt_secret(refresh_token)
            connection.scopes = scopes
            connection.is_connected = True
        await self.session.commit()
        return connection

    async def disconnect(self, brand_space_id: UUID, platform: str) -> SocialConnection:
        connection = await self.connections.get_by_platform(brand_space_id, platform)
        if not connection:
            raise NotFoundError("Social connection not found")
        connection.is_connected = False
        await self.session.commit()
        return connection

    async def publish(self, tenant_id: UUID, brand_space_id: UUID, platform: str, payload: dict) -> dict:
        connection = await self.connections.get_by_platform(brand_space_id, platform)
        if not connection or not connection.is_connected:
            raise NotFoundError("Platform not connected")
        content = await self.contents.get_scoped(payload["content_version_id"], tenant_id, brand_space_id)
        if not content:
            raise NotFoundError("Content version not found")
        assets = await self.assets.list_by_content(content.id)
        selected_asset_ids = {str(asset_id) for asset_id in payload.get("media_asset_ids", [])}
        media_assets = [
            asset.storage_path
            for asset in assets
            if asset.asset_role in {"render_export", "render_preview", "ai_image"}
            and (not selected_asset_ids or str(asset.id) in selected_asset_ids)
        ]
        generated = content.generated_payload or {}
        caption = payload.get("caption_override") or "\n\n".join(
            part for part in [generated.get("headline", ""), generated.get("body", ""), generated.get("cta", "")] if part
        )
        access_token = decrypt_secret(connection.access_token_encrypted)
        if not access_token:
            raise NotFoundError("Platform connection token unavailable")
        return {
            "platform": platform,
            "status": "accepted" if payload.get("publish_now", True) else "scheduled",
            "account_identifier": connection.account_identifier,
            "payload": {
                **payload,
                "caption": caption,
                "media_assets": media_assets,
            },
            "dispatch_metadata": {
                "provider_ready": True,
                "scopes": connection.scopes,
                "has_refresh_token": bool(decrypt_secret(connection.refresh_token_encrypted)),
            },
        }
