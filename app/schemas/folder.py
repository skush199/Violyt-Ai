from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class FolderCreateRequest(APIModel):
    name: str = Field(min_length=1)
    description: str | None = None


class FolderRenameRequest(APIModel):
    name: str = Field(min_length=1)


class FolderMoveRequest(APIModel):
    content_version_id: UUID
    folder_id: UUID

