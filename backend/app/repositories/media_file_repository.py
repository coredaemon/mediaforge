from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def delete_for_scan_session(self, scan_session_id: int) -> None:
        await self.session.execute(delete(MediaFile).where(MediaFile.scan_session_id == scan_session_id))
