"""Acknowledging episodes that TMDB does not know about.

Merged double-episode releases shift file numbering, so an episode can be
correct on disk while missing from TMDB season details. Such an episode must
not block TV planning once the user accepts it.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.models.enums import ReviewDecision
from backend.app.models.scan_session import ScanSession
from backend.app.models.tv_episode import TvEpisode
from backend.app.models.tv_season import TvSeason
from backend.app.models.tv_show import TvShow
from backend.app.services.tv_analysis_service import TvAnalysisService, TvEpisodeNotFoundError


async def _create_show_with_flagged_episode(db_session, tmp_path) -> tuple[int, int]:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
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
    episode = TvEpisode(
        show_id=show.id,
        season_id=season.id,
        season_number=2,
        episode_number=13,
        source_path=str(source / "The.Good.Place.S02E13.mkv"),
        needs_review=True,
        warning="Episode was not found in TMDB season details.",
    )
    db_session.add(episode)
    await db_session.commit()
    return show.id, episode.id


@pytest.mark.asyncio
async def test_acknowledge_episode_clears_review_flag(db_session, tmp_path) -> None:
    _, episode_id = await _create_show_with_flagged_episode(db_session, tmp_path)

    result = await TvAnalysisService(db_session).acknowledge_episode(episode_id)

    assert result.needs_review is False
    assert result.review_acknowledged is True


@pytest.mark.asyncio
async def test_acknowledge_episode_keeps_the_original_warning(db_session, tmp_path) -> None:
    """The reason stays visible after acknowledging; only the blocking flag clears."""
    _, episode_id = await _create_show_with_flagged_episode(db_session, tmp_path)

    result = await TvAnalysisService(db_session).acknowledge_episode(episode_id)

    assert result.warning == "Episode was not found in TMDB season details."


@pytest.mark.asyncio
async def test_acknowledge_unknown_episode_raises(db_session) -> None:
    with pytest.raises(TvEpisodeNotFoundError):
        await TvAnalysisService(db_session).acknowledge_episode(999999)


def test_acknowledge_episode_endpoint(client: TestClient, tmp_path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    created = client.post(
        "/scan-sessions",
        json={"source_path": str(source), "target_path": str(target)},
    )
    assert created.status_code == 200

    response = client.post("/tv-episodes/999999/acknowledge")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_show_warnings_exclude_session_wide_notes(db_session, tmp_path) -> None:
    """Session-wide AI notes must not be copied into every show card."""
    from backend.app.schemas.tv import TvFolderContext

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()

    service = TvAnalysisService(db_session)
    context = TvFolderContext(root_path=str(source), folders=[], files=[], possible_show_titles=[])
    grouping = {
        "shows": [{"local_group_id": "g1", "probable_title": "Show One", "seasons": []}],
        "warnings": ["session-wide grouping note"],
    }
    audit = {
        "shows": [{"local_group_id": "g1", "issues": ["this show only issue"]}],
        "global_warnings": ["session-wide audit note"],
    }

    shows = await service._persist(scan_session.id, context, grouping, {"shows": {}}, audit)

    assert shows[0].warnings == ["this show only issue"]
