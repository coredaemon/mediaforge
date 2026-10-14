"""Regressions from a real session: a manually matched file that could not be planned.

The file name was unparseable, so the item stayed UNKNOWN; a manual TMDB-ID match
marked it MATCHED without giving it a type, and a later re-scan recreated every
file row, cutting the item off from its video. Either alone made planning fail
with "none could be planned with the current metadata".
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.models.enums import MediaFileKind, MediaItemStatus, MediaType, OperationType
from backend.app.models.media_file import MediaFile
from backend.app.models.media_item import MediaItem
from backend.app.models.scan_session import ScanSession
from backend.app.models.tv_episode import TvEpisode
from backend.app.models.tv_season import TvSeason
from backend.app.models.tv_show import TvShow
from backend.app.repositories.plan_operation_repository import PlanOperationRepository
from backend.app.schemas.tmdb import TmdbDetailsResult
from backend.app.services.parser_service import ParserService
from backend.app.services.planning_service import PlanningService
from backend.app.services.scanner_service import ScannerService
from backend.app.services.tmdb_service import TMDBService
from backend.tests.fakes import FakeTmdbClient


async def _scanned_session(db_session, tmp_path: Path, names: list[str]) -> ScanSession:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    for name in names:
        (source / name).write_bytes(b"video")
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)
    await ScannerService(db_session).discover(scan_session.id)
    return scan_session


async def _video_files(db_session, scan_session_id: int) -> list[MediaFile]:
    result = await db_session.execute(
        select(MediaFile).where(
            MediaFile.scan_session_id == scan_session_id,
            MediaFile.kind == MediaFileKind.VIDEO,
        )
    )
    return list(result.scalars().all())


# --- re-running discover --------------------------------------------------


@pytest.mark.asyncio
async def test_rediscover_keeps_files_linked_to_their_items(db_session, tmp_path: Path) -> None:
    scan_session = await _scanned_session(db_session, tmp_path, ["The.Matrix.1999.mkv"])
    await ParserService(db_session).parse_scan_session(scan_session.id)
    [before] = await _video_files(db_session, scan_session.id)
    assert before.media_item_id is not None

    await ScannerService(db_session).discover(scan_session.id)

    [after] = await _video_files(db_session, scan_session.id)
    assert after.id == before.id
    assert after.media_item_id == before.media_item_id


@pytest.mark.asyncio
async def test_rediscover_picks_up_new_files_and_drops_vanished_ones(db_session, tmp_path: Path) -> None:
    scan_session = await _scanned_session(db_session, tmp_path, ["a.mkv", "b.mkv"])
    source = Path(scan_session.source_path)
    (source / "b.mkv").unlink()
    (source / "c.mkv").write_bytes(b"video")

    await ScannerService(db_session).discover(scan_session.id)

    names = sorted(f.file_name for f in await _video_files(db_session, scan_session.id))
    assert names == ["a.mkv", "c.mkv"]


@pytest.mark.asyncio
async def test_rediscover_refreshes_metadata_of_changed_files(db_session, tmp_path: Path) -> None:
    scan_session = await _scanned_session(db_session, tmp_path, ["a.mkv"])
    (Path(scan_session.source_path) / "a.mkv").write_bytes(b"much longer video payload")

    await ScannerService(db_session).discover(scan_session.id)

    [media_file] = await _video_files(db_session, scan_session.id)
    assert media_file.size_bytes == len(b"much longer video payload")


@pytest.mark.asyncio
async def test_rediscover_after_tv_analysis_does_not_break_episode_links(db_session, tmp_path: Path) -> None:
    """tv_episodes.source_file_id is a foreign key into media_files."""
    scan_session = await _scanned_session(db_session, tmp_path, ["Show S01E01.mkv", "Show S01E02.mkv"])
    files = sorted(await _video_files(db_session, scan_session.id), key=lambda f: f.file_name)
    show = TvShow(scan_session_id=scan_session.id, title="Show", tmdb_id=1, needs_review=False)
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    episodes = []
    for number, media_file in enumerate(files, start=1):
        episode = TvEpisode(
            show_id=show.id, season_id=season.id, source_file_id=media_file.id,
            season_number=1, episode_number=number, source_path=media_file.path,
        )
        db_session.add(episode)
        episodes.append(episode)
    await db_session.commit()
    kept_file_id = files[0].id
    (Path(scan_session.source_path) / "Show S01E02.mkv").unlink()

    result = await ScannerService(db_session).discover(scan_session.id)

    assert result.error_message is None
    await db_session.refresh(episodes[0])
    await db_session.refresh(episodes[1])
    assert episodes[0].source_file_id == kept_file_id
    assert episodes[1].source_file_id is None


# --- media type after a TMDB match ----------------------------------------


def _matrix_details() -> TmdbDetailsResult:
    return TmdbDetailsResult(tmdb_id=603, media_type="movie", title="The Matrix", year=1999)


class _DetailsClient(FakeTmdbClient):
    async def get_movie_details(self, tmdb_id, language="ru-RU"):
        return _matrix_details()


@pytest.mark.asyncio
async def test_manual_tmdb_id_match_gives_an_unknown_item_its_type(db_session, tmp_path: Path) -> None:
    scan_session = await _scanned_session(db_session, tmp_path, ["unparseable.mp4"])
    await ParserService(db_session).parse_scan_session(scan_session.id)
    item = (await db_session.execute(select(MediaItem))).scalars().one()
    item.media_type = MediaType.UNKNOWN
    await db_session.commit()

    service = TMDBService(db_session, client=_DetailsClient(movie_results=[], tv_results=[]))
    await service.manual_lookup(item.id, tmdb_id=603, media_type="movie", select=True)

    await db_session.refresh(item)
    assert item.status == MediaItemStatus.MATCHED
    assert item.media_type == MediaType.MOVIE

    plan = await PlanningService(db_session).create_plan_for_scan_session(scan_session.id)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)
    assert any(op.operation_type == OperationType.MOVE_FILE for op in operations)


@pytest.mark.asyncio
async def test_planner_falls_back_to_the_tmdb_type_for_existing_unknown_items(
    db_session, tmp_path: Path
) -> None:
    """Items already saved as MATCHED + UNKNOWN before the fix must still plan."""
    scan_session = await _scanned_session(db_session, tmp_path, ["unparseable.mp4"])
    await ParserService(db_session).parse_scan_session(scan_session.id)
    item = (await db_session.execute(select(MediaItem))).scalars().one()
    item.media_type = MediaType.UNKNOWN
    item.status = MediaItemStatus.MATCHED
    item.needs_review = False
    item.tmdb_id = 603
    item.tmdb_media_type = "movie"
    item.matched_title = "The Matrix"
    item.matched_year = 1999
    await db_session.commit()

    plan = await PlanningService(db_session).create_plan_for_scan_session(scan_session.id)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)

    moves = [op for op in operations if op.operation_type == OperationType.MOVE_FILE]
    assert len(moves) == 1
    assert moves[0].target_path.endswith("The Matrix (1999).mp4")
