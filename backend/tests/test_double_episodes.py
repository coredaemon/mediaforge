"""Merged (double) episode releases.

Some releases put two aired episodes in one file: `S02E01E02`. Media servers
expect those named `S02E01-E02`. Detection must be deterministic from the file
name — the AI grouping only sees the first number and silently drops the second.
"""

import pytest

from backend.app.utils.media_name_parser import parse_episode_range
from backend.app.utils.target_paths import format_episode_filename


@pytest.mark.parametrize(
    "stem, expected",
    [
        ("The.Good.Place.S02E01E02.1080p.WEB-DL.mkv", (2, 1, 2)),
        ("The.Good.Place.S04E13E14.1080p.TVShows.mkv", (4, 13, 14)),
        ("Show.S01E01-E02.mkv", (1, 1, 2)),
        ("Show.S01E01-02.mkv", (1, 1, 2)),
        ("Show S03E05E06 1080p.mkv", (3, 5, 6)),
        ("Show.1x01x02.mkv", (1, 1, 2)),
    ],
)
def test_parses_merged_episode_ranges(stem: str, expected: tuple[int, int, int]) -> None:
    result = parse_episode_range(stem)

    assert result is not None
    assert (result.season_number, result.episode_number, result.episode_number_end) == expected


@pytest.mark.parametrize(
    "stem",
    [
        "The.Good.Place.S02E13.1080p.WEB-DL.mkv",
        "Derry.Girls.S01E01.WEBDL.1080p.mkv",
        "Show.S01E01.1080p.x264.mkv",
    ],
)
def test_single_episode_has_no_range_end(stem: str) -> None:
    result = parse_episode_range(stem)

    assert result is not None
    assert result.episode_number_end is None


def test_resolution_in_name_is_not_read_as_episode_range() -> None:
    """1080p must never be mistaken for an episode number."""
    result = parse_episode_range("Show.S01E01.1080p.WEB-DL.mkv")

    assert result is not None
    assert result.episode_number == 1
    assert result.episode_number_end is None


def test_descending_range_is_rejected() -> None:
    assert parse_episode_range("Show.S01E05E02.mkv") is None


def test_double_episode_filename_uses_range_form() -> None:
    name = format_episode_filename("В лучшем мире", 2, 1, ".mkv", episode_number_end=2)

    assert name == "В лучшем мире S02E01-E02.mkv"


def test_double_episode_filename_with_title() -> None:
    name = format_episode_filename(
        "В лучшем мире",
        2,
        1,
        ".mkv",
        episode_title="Всё прекрасно",
        episode_number_end=2,
    )

    assert name == "В лучшем мире - S02E01-E02 - Всё прекрасно.mkv"


def test_single_episode_filename_is_unchanged() -> None:
    assert format_episode_filename("Дрянь", 1, 3, ".mkv") == "Дрянь S01E03.mkv"


@pytest.mark.asyncio
async def test_merged_episode_is_planned_with_range_name(db_session, tmp_path) -> None:
    """A merged release must be planned as S02E01-E02, not as a single episode."""
    from backend.app.models.enums import MediaFileKind, ReviewDecision
    from backend.app.models.media_file import MediaFile
    from backend.app.models.scan_session import ScanSession
    from backend.app.models.tv_episode import TvEpisode
    from backend.app.models.tv_season import TvSeason
    from backend.app.models.tv_show import TvShow
    from backend.app.repositories.plan_operation_repository import PlanOperationRepository
    from backend.app.services.tv_planning_service import TvPlanningService

    source = tmp_path / "source"
    target = tmp_path / "target"
    season_source = source / "The Good Place" / "Season 02"
    season_source.mkdir(parents=True)
    target.mkdir()
    video = season_source / "The.Good.Place.S02E01E02.1080p.WEB-DL.mkv"
    video.write_bytes(b"episode")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.flush()
    media_file = MediaFile(
        scan_session_id=scan_session.id,
        path=str(video.resolve()),
        file_name=video.name,
        extension=".mkv",
        size_bytes=video.stat().st_size,
        modified_at=None,
        kind=MediaFileKind.VIDEO,
        is_video=True,
    )
    db_session.add(media_file)
    await db_session.flush()
    show = TvShow(
        scan_session_id=scan_session.id,
        local_group_id="good-place",
        title="В лучшем мире",
        year=2016,
        tmdb_id=66573,
        review_decision=ReviewDecision.APPROVED,
        needs_review=False,
    )
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=2, title="Season 02")
    db_session.add(season)
    await db_session.flush()
    db_session.add(
        TvEpisode(
            show_id=show.id,
            season_id=season.id,
            source_file_id=media_file.id,
            season_number=2,
            episode_number=1,
            episode_number_end=2,
            source_path=str(video.resolve()),
            needs_review=False,
        )
    )
    await db_session.commit()

    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)
    targets = [op.target_path or "" for op in operations]

    assert any(t.endswith("В лучшем мире S02E01-E02.mkv") for t in targets), targets
    assert any(t.endswith("В лучшем мире S02E01-E02.nfo") for t in targets), targets


@pytest.mark.asyncio
async def test_flagged_episode_is_still_planned(db_session, tmp_path) -> None:
    """A warning must never silently drop a file from the plan."""
    from backend.app.models.enums import MediaFileKind, ReviewDecision
    from backend.app.models.media_file import MediaFile
    from backend.app.models.scan_session import ScanSession
    from backend.app.models.tv_episode import TvEpisode
    from backend.app.models.tv_season import TvSeason
    from backend.app.models.tv_show import TvShow
    from backend.app.repositories.plan_operation_repository import PlanOperationRepository
    from backend.app.services.tv_planning_service import TvPlanningService

    source = tmp_path / "source"
    target = tmp_path / "target"
    season_source = source / "Show" / "Season 02"
    season_source.mkdir(parents=True)
    target.mkdir()
    video = season_source / "Show.S02E13.mkv"
    video.write_bytes(b"episode")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.flush()
    media_file = MediaFile(
        scan_session_id=scan_session.id,
        path=str(video.resolve()),
        file_name=video.name,
        extension=".mkv",
        size_bytes=video.stat().st_size,
        modified_at=None,
        kind=MediaFileKind.VIDEO,
        is_video=True,
    )
    db_session.add(media_file)
    await db_session.flush()
    show = TvShow(
        scan_session_id=scan_session.id,
        local_group_id="show",
        title="Сериал",
        year=2016,
        tmdb_id=1,
        review_decision=ReviewDecision.APPROVED,
        needs_review=False,
    )
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=2, title="Season 02")
    db_session.add(season)
    await db_session.flush()
    db_session.add(
        TvEpisode(
            show_id=show.id,
            season_id=season.id,
            source_file_id=media_file.id,
            season_number=2,
            episode_number=13,
            source_path=str(video.resolve()),
            needs_review=True,
            warning="В TMDB у сезона 2 нет серии 13 — файл будет разложен по номеру из имени.",
        )
    )
    await db_session.commit()

    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)
    moved = [op.source_path for op in operations if op.operation_type.value == "MOVE_FILE"]

    assert str(video.resolve()) in moved
