from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaItemStatus, MediaType, ReviewDecision
from ..models.media_item import MediaItem


class MediaItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, media_item: MediaItem) -> MediaItem:
        self.session.add(media_item)
        await self.session.flush()
        return media_item

    async def get_by_id(self, media_item_id: int) -> MediaItem | None:
        return await self.session.get(MediaItem, media_item_id)

    async def list_by_scan_session(self, scan_session_id: int) -> Sequence[MediaItem]:
        result = await self.session.execute(
            select(MediaItem).where(MediaItem.scan_session_id == scan_session_id).order_by(MediaItem.id.asc())
        )
        return result.scalars().all()

    async def list_matchable_by_scan_session(self, scan_session_id: int) -> Sequence[MediaItem]:
        result = await self.session.execute(
            select(MediaItem)
            .where(
                MediaItem.scan_session_id == scan_session_id,
                MediaItem.media_type == MediaType.MOVIE,
                MediaItem.status != MediaItemStatus.IGNORED,
                MediaItem.parsed_title.is_not(None),
            )
            .order_by(MediaItem.id.asc())
        )
        return result.scalars().all()

    async def list_matched_by_scan_session(self, scan_session_id: int) -> Sequence[MediaItem]:
        result = await self.session.execute(
            select(MediaItem)
            .where(
                MediaItem.scan_session_id == scan_session_id,
                MediaItem.status == MediaItemStatus.MATCHED,
            )
            .order_by(MediaItem.id.asc())
        )
        return result.scalars().all()

    async def list_plannable_by_scan_session(self, scan_session_id: int) -> Sequence[MediaItem]:
        result = await self.session.execute(
            select(MediaItem)
            .where(
                MediaItem.scan_session_id == scan_session_id,
                MediaItem.status == MediaItemStatus.MATCHED,
                MediaItem.review_decision.not_in([ReviewDecision.IGNORED, ReviewDecision.DEFERRED]),
            )
            .order_by(MediaItem.id.asc())
        )
        return result.scalars().all()

    async def count_review_excluded_by_scan_session(self, scan_session_id: int) -> dict[str, int]:
        items = await self.list_by_scan_session(scan_session_id)
        ignored = 0
        deferred = 0
        pending = 0
        for item in items:
            if item.review_decision == ReviewDecision.IGNORED:
                ignored += 1
            elif item.review_decision == ReviewDecision.DEFERRED:
                deferred += 1
            elif item.review_decision == ReviewDecision.PENDING and item.status == MediaItemStatus.MATCHED:
                pending += 1
        return {"ignored": ignored, "deferred": deferred, "pending": pending}
