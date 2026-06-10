from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaFileKind
from ..models.media_file import MediaFile


class MediaFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, media_file: MediaFile) -> MediaFile:
        self.session.add(media_file)
        await self.session.flush()
        return media_file

    async def list_for_scan_session(self, scan_session_id: int) -> Sequence[MediaFile]:
        result = await self.session.execute(
            select(MediaFile).where(MediaFile.scan_session_id == scan_session_id).order_by(MediaFile.path.asc())
        )
        return result.scalars().all()

    async def list_by_kind(self, scan_session_id: int, kind: MediaFileKind) -> Sequence[MediaFile]:
        result = await self.session.execute(
            select(MediaFile)
            .where(MediaFile.scan_session_id == scan_session_id, MediaFile.kind == kind)
            .order_by(MediaFile.path.asc())
        )
        return result.scalars().all()

    async def link_to_media_item(self, media_file: MediaFile, media_item_id: int) -> MediaFile:
        media_file.media_item_id = media_item_id
        await self.session.flush()
        return media_file

    async def delete_for_scan_session(self, scan_session_id: int) -> None:
        await self.session.execute(delete(MediaFile).where(MediaFile.scan_session_id == scan_session_id))
