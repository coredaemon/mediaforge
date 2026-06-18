from pathlib import Path

from backend.app.services.media_classification_service import MediaClassificationService
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.scanner_service import ScannerService


async def _scan(db_session, source: Path, target: Path):
    session = await ScanSessionService(db_session).create_scan_session(str(source), str(target))
    await ScannerService(db_session).discover(session.id)
    return session


async def test_classification_detects_tv_folder_with_season_folders(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    season = source / "Test Show" / "Season 01"
    target = tmp_path / "target"
    season.mkdir(parents=True)
    target.mkdir()
    (season / "Test Show S01E01.mkv").write_bytes(b"video")
    (season / "Test Show S01E02.mkv").write_bytes(b"video")

    scan = await _scan(db_session, source, target)
    result = await MediaClassificationService(db_session).classify(scan.id)

    assert result.content_type == "tv"
    assert result.video_files == 2
    assert result.tv_like_files == 2
    assert result.needs_user_decision is False


async def test_classification_detects_movies_folder(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "Movie.Name.2024.mkv").write_bytes(b"video")

    scan = await _scan(db_session, source, target)
    result = await MediaClassificationService(db_session).classify(scan.id)

    assert result.content_type == "movies"
    assert result.movie_like_files == 1


async def test_classification_detects_mixed_folder(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "Movie.Name.2024.mkv").write_bytes(b"video")
    (source / "Show.Name.S01E01.mkv").write_bytes(b"video")

    scan = await _scan(db_session, source, target)
    result = await MediaClassificationService(db_session).classify(scan.id)

    assert result.content_type == "mixed"
    assert result.mixed is True


async def test_classification_unknown_when_no_video_and_returns_warning(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "archive.rar").write_bytes(b"data")
    (source / "readme.txt").write_text("notes")

    scan = await _scan(db_session, source, target)
    result = await MediaClassificationService(db_session).classify(scan.id)

    assert result.content_type == "unknown"
    assert result.total_files == 2
    assert result.video_files == 0
    assert result.needs_user_decision is True
    assert result.warnings
    assert {item.extension for item in result.ignored_extensions} == {".rar", ".txt"}
