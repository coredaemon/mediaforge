from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaFileKind, ScanSessionStatus
from backend.app.repositories.media_file_repository import MediaFileRepository
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.scanner_service import ScannerService
from backend.app.utils.paths import classify_media_file_kind


def test_classify_media_file_kind_by_extension() -> None:
    assert classify_media_file_kind("movie.mkv") == MediaFileKind.VIDEO
    assert classify_media_file_kind("episode.MKV") == MediaFileKind.VIDEO
    assert classify_media_file_kind("broadcast.ts") == MediaFileKind.VIDEO
    assert classify_media_file_kind("disc.m2ts") == MediaFileKind.VIDEO
    assert classify_media_file_kind("web.webm") == MediaFileKind.VIDEO
    assert classify_media_file_kind("old.flv") == MediaFileKind.VIDEO
    assert classify_media_file_kind("movie.srt") == MediaFileKind.SUBTITLE
    assert classify_media_file_kind("movie.nfo") == MediaFileKind.SIDECAR
    assert classify_media_file_kind("notes.txt") == MediaFileKind.OTHER


async def test_scanner_discovers_files_and_updates_session(db_session: AsyncSession, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "Movie.1999.mkv").write_bytes(b"video")
    (source_path / "Movie.1999.srt").write_text("subtitle", encoding="utf-8")
    (source_path / "movie.nfo").write_text("metadata", encoding="utf-8")
    (source_path / "readme.txt").write_text("notes", encoding="utf-8")

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    updated_session = await ScannerService(db_session).discover(scan_session.id)
    media_files = await MediaFileRepository(db_session).list_for_scan_session(scan_session.id)
    kinds_by_name = {media_file.file_name: media_file.kind for media_file in media_files}

    assert updated_session.status == ScanSessionStatus.DISCOVERED
    assert len(media_files) == 4
    assert kinds_by_name == {
        "Movie.1999.mkv": MediaFileKind.VIDEO,
        "Movie.1999.srt": MediaFileKind.SUBTITLE,
        "movie.nfo": MediaFileKind.SIDECAR,
        "readme.txt": MediaFileKind.OTHER,
    }


async def test_scanner_counts_nested_tv_common_video_extensions(db_session: AsyncSession, tmp_path) -> None:
    source_path = tmp_path / "source"
    season_path = source_path / "Test Show" / "Season 01"
    season_path.mkdir(parents=True)
    target_path = tmp_path / "library"
    target_path.mkdir()
    for name in ["Test Show S01E01.MKV", "Test Show S01E02.m2ts", "Test Show S01E03.webm", "Test Show S01E04.ts"]:
        (season_path / name).write_bytes(b"video")

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    await ScannerService(db_session).discover(scan_session.id)
    media_files = await MediaFileRepository(db_session).list_for_scan_session(scan_session.id)

    assert len(media_files) == 4
    assert all(media_file.kind == MediaFileKind.VIDEO for media_file in media_files)
    assert all(media_file.is_video for media_file in media_files)
