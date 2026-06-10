from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import ScanSessionStatus
from ..models.scan_session import ScanSession


class ScanSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, source_path: str, target_path: str) -> ScanSession:
        scan_session = ScanSession(source_path=source_path, target_path=target_path)
        self.session.add(scan_session)
        await self.session.flush()
        await self.session.refresh(scan_session)
        return scan_session

    async def get(self, scan_session_id: int) -> ScanSession | None:
        return await self.session.get(ScanSession, scan_session_id)

    async def list_recent(self, limit: int = 50) -> Sequence[ScanSession]:
        result = await self.session.execute(
            select(ScanSession).order_by(ScanSession.created_at.desc(), ScanSession.id.desc()).limit(limit)
        )
        return result.scalars().all()

    async def set_status(
        self,
        scan_session: ScanSession,
        status: ScanSessionStatus,
        error_message: str | None = None,
    ) -> ScanSession:
        scan_session.status = status
        scan_session.error_message = error_message
        await self.session.flush()
        await self.session.refresh(scan_session)
        return scan_session
