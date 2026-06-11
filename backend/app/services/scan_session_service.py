from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.scan_session import ScanSession
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.media_item_repository import MediaItemRepository
from ..repositories.recognition_memory_repository import RecognitionMemoryRepository
from ..repositories.scan_session_repository import ScanSessionRepository


class ScanSessionNotFoundError(LookupError):
    """Raised when a scan session id does not exist."""


class ScanSessionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.scan_sessions = ScanSessionRepository(session)
        self.media_items = MediaItemRepository(session)
        self.media_files = MediaFileRepository(session)
        self.memory = RecognitionMemoryRepository(session)

    async def create_scan_session(self, source_path: str, target_path: str) -> ScanSession:
        scan_session = await self.scan_sessions.create(source_path=source_path, target_path=target_path)
        await self.session.commit()
        await self.session.refresh(scan_session)
        return scan_session

    async def list_scan_sessions(self, limit: int = 50) -> Sequence[ScanSession]:
        return await self.scan_sessions.list_recent(limit=limit)

    async def get_scan_session(self, scan_session_id: int) -> ScanSession:
        scan_session = await self.scan_sessions.get(scan_session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")
        return scan_session

    async def delete_scan_session(self, scan_session_id: int) -> int:
        scan_session = await self.scan_sessions.get(scan_session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")

        items = await self.media_items.list_by_scan_session(scan_session_id)
        item_ids = [item.id for item in items]
        await self.memory.detach_corrections_for_media_items(item_ids)
        await self.media_files.delete_for_scan_session(scan_session_id)
        await self.scan_sessions.delete(scan_session)
        await self.session.commit()
        return scan_session_id
