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


@pytest.mark.asyncio
async def test_reanalysis_keeps_manual_tmdb_choice(db_session, tmp_path, monkeypatch) -> None:
    """Re-running the analysis must not discard a match the user picked by hand."""
    from backend.app.models.media_file import MediaFile
    from backend.app.models.enums import MediaFileKind

    source = tmp_path / "source"
    target = tmp_path / "target"
    season_dir = source / "Some Show" / "Season 01"
    season_dir.mkdir(parents=True)
    target.mkdir()
    video = season_dir / "Some.Show.S01E01.mkv"
    video.write_bytes(b"episode")

    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.flush()
    db_session.add(
        MediaFile(
            scan_session_id=scan_session.id,
            path=str(video.resolve()),
            file_name=video.name,
            extension=".mkv",
            size_bytes=video.stat().st_size,
            modified_at=None,
            kind=MediaFileKind.VIDEO,
            is_video=True,
        )
    )
    show = TvShow(
        scan_session_id=scan_session.id,
        local_group_id="show-1",
        title="Выбрано вручную",
        year=2016,
        tmdb_id=424242,
        match_source="manual_tmdb_id",
        review_decision=ReviewDecision.MANUAL_OVERRIDE,
        needs_review=False,
    )
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    db_session.add(
        TvEpisode(
            show_id=show.id,
            season_id=season.id,
            season_number=1,
            episode_number=1,
            source_path=str(video.resolve()),
        )
    )
    await db_session.commit()

    service = TvAnalysisService(db_session)
    collected = await service._collect_manual_choices(scan_session.id)
    assert collected and collected[0]["tmdb_id"] == 424242

    # A fresh analysis produced a different (automatic) match for the same files.
    rebuilt = TvShow(
        scan_session_id=scan_session.id,
        local_group_id="show-1",
        title="Автоматическое совпадение",
        tmdb_id=999,
        match_source="local_llm_grouping",
        review_decision=ReviewDecision.PENDING,
        needs_review=False,
    )
    db_session.add(rebuilt)
    await db_session.flush()
    rebuilt_season = TvSeason(show_id=rebuilt.id, season_number=1, title="Season 01")
    db_session.add(rebuilt_season)
    await db_session.flush()
    db_session.add(
        TvEpisode(
            show_id=rebuilt.id,
            season_id=rebuilt_season.id,
            season_number=1,
            episode_number=1,
            source_path=str(video.resolve()),
        )
    )
    await db_session.commit()

    applied = []

    async def fake_lookup(show_id, *, tmdb_id=None, imdb_id=None, tvdb_id=None, select=False):
        applied.append((show_id, tmdb_id))
        return rebuilt

    monkeypatch.setattr(service, "lookup_show_tmdb", fake_lookup)
    fresh = await service.get_show(rebuilt.id)
    await service._restore_manual_choices([fresh], collected)

    assert applied == [(rebuilt.id, 424242)]
    assert fresh.review_decision == ReviewDecision.MANUAL_OVERRIDE


@pytest.mark.asyncio
async def test_confident_match_needs_no_confirmation_despite_ai_remark(db_session, tmp_path) -> None:
    """A completeness remark ("season 3 is missing its finale") must not gate a solid match."""
    from backend.app.schemas.tv import TvFolderContext

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()

    grouping = {"shows": [{"local_group_id": "g1", "probable_title": "The Good Place", "seasons": []}]}
    tmdb_data = {"shows": {"g1": {"details": {"tmdb_id": 66573, "title": "В лучшем мире"}, "source": "tmdb"}}}
    audit = {
        "shows": [
            {
                "local_group_id": "g1",
                "selected_tmdb_id": 66573,
                "confidence": 0.97,
                "manual_review_required": True,
                "issues": ["В третьем сезоне отсутствует тринадцатый эпизод."],
            }
        ]
    }
    context = TvFolderContext(root_path=str(source), folders=[], files=[], possible_show_titles=[])

    shows = await TvAnalysisService(db_session)._persist(scan_session.id, context, grouping, tmdb_data, audit)

    assert shows[0].needs_review is False
    assert shows[0].warnings == ["В третьем сезоне отсутствует тринадцатый эпизод."]


@pytest.mark.asyncio
async def test_uncertain_match_still_asks_for_confirmation(db_session, tmp_path) -> None:
    from backend.app.schemas.tv import TvFolderContext

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()

    grouping = {"shows": [{"local_group_id": "g1", "probable_title": "Неизвестный сериал", "seasons": []}]}
    tmdb_data = {"shows": {"g1": {"details": {"tmdb_id": 5, "title": "Похожий сериал"}, "source": "tmdb"}}}
    audit = {
        "shows": [
            {"local_group_id": "g1", "selected_tmdb_id": 5, "confidence": 0.4, "manual_review_required": True}
        ]
    }
    context = TvFolderContext(root_path=str(source), folders=[], files=[], possible_show_titles=[])

    shows = await TvAnalysisService(db_session)._persist(scan_session.id, context, grouping, tmdb_data, audit)

    assert shows[0].needs_review is True


@pytest.mark.asyncio
async def test_show_without_tmdb_match_needs_review(db_session, tmp_path) -> None:
    from backend.app.schemas.tv import TvFolderContext

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()

    grouping = {"shows": [{"local_group_id": "g1", "probable_title": "Ничего не найдено", "seasons": []}]}
    context = TvFolderContext(root_path=str(source), folders=[], files=[], possible_show_titles=[])

    shows = await TvAnalysisService(db_session)._persist(
        scan_session.id, context, grouping, {"shows": {}}, {"shows": [{"local_group_id": "g1", "confidence": 0.9}]}
    )

    assert shows[0].needs_review is True
