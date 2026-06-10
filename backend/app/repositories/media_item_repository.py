from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
