from pathlib import Path

import pytest

from backend.app.models.scan_session import ScanSession
from backend.app.services.scanner_service import ScannerService
from backend.app.services.tv_folder_context import TvFolderContextBuilder


@pytest.mark.asyncio
async def test_tv_folder_context_includes_cyrillic_and_sidecar_ids(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    season = source / "Тестовый сериал" / "Сезон 1"
    season.mkdir(parents=True)
    target.mkdir()
    (season / "Тестовый сериал S01E01.mkv").write_text("video")
    (season / "tvshow.nfo").write_text(
        "<tvshow><title>Тестовый сериал</title><uniqueid type='tmdb'>123</uniqueid><uniqueid type='tvdb'>456</uniqueid></tvshow>",
        encoding="utf-8",
    )
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)

    await ScannerService(db_session).discover(scan_session.id)
    context = await TvFolderContextBuilder(db_session).build(scan_session.id)

    assert "Тестовый сериал" in context.possible_show_titles
    assert any(file.relative_path.endswith("S01E01.mkv") and file.season_number == 1 for file in context.files)
    nfo = next(file for file in context.files if file.file_name == "tvshow.nfo")
    assert nfo.sidecar_ids
    assert nfo.sidecar_ids["tmdb_id"] == 123
    assert nfo.sidecar_ids["tvdb_id"] == 456
