from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ReviewStatus
from app.core.exceptions import LifecycleError
from app.core.exceptions import NotFoundError
from app.repositories.content import ContentRepository
from app.models.collaboration import ReviewComment, ReviewLink
from app.repositories.collaboration import ReviewCommentRepository, ReviewLinkRepository


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.links = ReviewLinkRepository(session)
        self.comments = ReviewCommentRepository(session)
        self.contents = ContentRepository(session)

    async def create_link(self, tenant_id: UUID, brand_space_id: UUID, content_version_id: UUID, created_by: UUID, title: str | None, allow_external_comments: bool) -> ReviewLink:
        content = await self.contents.get_scoped(content_version_id, tenant_id, brand_space_id)
        if not content:
            raise NotFoundError("Content version not found")
        review_link = ReviewLink(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content_version_id=content_version_id,
            created_by=created_by,
            token=secrets.token_urlsafe(24),
            title=title,
            allow_external_comments=allow_external_comments,
            status="pending",
        )
        await self.links.add(review_link)
        await self.session.commit()
        return review_link

    async def get_by_token(self, token: str) -> tuple[ReviewLink, list[ReviewComment]]:
        link = await self.links.get_by_token(token)
        if not link:
            raise NotFoundError("Review link not found")
        comments = await self.comments.list_for_link(link.id)
        return link, comments

    async def add_comment(self, review_link_id: UUID, tenant_id: UUID, brand_space_id: UUID, body: str, author_user_id: UUID | None = None, external_author_name: str | None = None) -> ReviewComment:
        link = await self.links.get(review_link_id)
        if not link:
            raise NotFoundError("Review link not found")
        if author_user_id is None and not link.allow_external_comments:
            raise LifecycleError("External comments are disabled for this review link")
        comment = ReviewComment(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            review_link_id=review_link_id,
            author_user_id=author_user_id,
            external_author_name=external_author_name,
            body=body,
        )
        await self.comments.add(comment)
        await self.session.commit()
        return comment

    async def update_status(self, review_link_id: UUID, status: str) -> ReviewLink:
        link = await self.links.get(review_link_id)
        if not link:
            raise NotFoundError("Review link not found")
        if status not in {ReviewStatus.PENDING, ReviewStatus.APPROVED, ReviewStatus.NEEDS_CHANGES}:
            raise LifecycleError("Invalid review status")
        link.status = status
        await self.session.commit()
        return link
