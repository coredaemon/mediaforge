from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaType, ScanSessionStatus
from backend.app.repositories.media_file_repository import MediaFileRepository
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.services.parser_service import ParserService
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.scanner_service import ScannerService


async def test_parser_creates_items_for_video_files_only(db_session: AsyncSession, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "The.Matrix.1999.1080p.BluRay.x264.mkv").write_bytes(b"video")
    (source_path / "The.Matrix.1999.srt").write_text("subtitle", encoding="utf-8")
    (source_path / "Hannibal.S01E01.mkv").write_bytes(b"video")
    (source_path / "readme.txt").write_text("notes", encoding="utf-8")

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    await ScannerService(db_session).discover(scan_session.id)
    parsed_session = await ParserService(db_session).parse_scan_session(scan_session.id)

    items = await MediaItemRepository(db_session).list_by_scan_session(scan_session.id)
    files = await MediaFileRepository(db_session).list_for_scan_session(scan_session.id)
    videos = [media_file for media_file in files if media_file.is_video]
    non_videos = [media_file for media_file in files if not media_file.is_video]
    items_by_title = {item.parsed_title: item for item in items}

    assert parsed_session.status == ScanSessionStatus.PARSED
    assert len(items) == 2
    assert items_by_title["The Matrix"].media_type == MediaType.MOVIE
    assert items_by_title["Hannibal"].media_type == MediaType.TV_EPISODE
    assert all(video.media_item_id is not None for video in videos)
    assert all(media_file.media_item_id is None for media_file in non_videos)


async def test_parser_is_idempotent_for_linked_video_files(db_session: AsyncSession, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "Matrix.1999.mkv").write_bytes(b"video")

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    await ScannerService(db_session).discover(scan_session.id)
    await ParserService(db_session).parse_scan_session(scan_session.id)
    await ParserService(db_session).parse_scan_session(scan_session.id)

    items = await MediaItemRepository(db_session).list_by_scan_session(scan_session.id)

    assert len(items) == 1
