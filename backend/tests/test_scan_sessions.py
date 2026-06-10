from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import ScanSessionStatus
from backend.app.services.scan_session_service import ScanSessionService


async def test_create_scan_session(db_session: AsyncSession, tmp_path) -> None:
    service = ScanSessionService(db_session)

    scan_session = await service.create_scan_session(
        source_path=str(tmp_path / "inbox"),
        target_path=str(tmp_path / "library"),
    )

    assert scan_session.id is not None
    assert scan_session.status == ScanSessionStatus.CREATED


async def test_list_scan_sessions(db_session: AsyncSession, tmp_path) -> None:
    service = ScanSessionService(db_session)
    await service.create_scan_session(str(tmp_path / "inbox-1"), str(tmp_path / "library"))
    await service.create_scan_session(str(tmp_path / "inbox-2"), str(tmp_path / "library"))

    scan_sessions = await service.list_scan_sessions()

    assert len(scan_sessions) == 2
    assert {scan_session.source_path for scan_session in scan_sessions} == {
        str(tmp_path / "inbox-1"),
        str(tmp_path / "inbox-2"),
    }
