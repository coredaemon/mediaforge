from pathlib import Path

import pytest

from backend.app.models.enums import MediaFileKind, ReviewDecision
from backend.app.models.media_file import MediaFile
from backend.app.models.scan_session import ScanSession
from backend.app.models.tv_episode import TvEpisode
from backend.app.models.tv_season import TvSeason
from backend.app.models.tv_show import TvShow
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.services.media_classification_service import MediaClassificationService
from backend.app.services.parser_service import ParserService
from backend.app.schemas.tmdb import TmdbDetailsResult, TmdbEpisodeResult, TmdbExternalIds, TmdbSearchResult, TmdbSeasonDetailsResult
from backend.app.services.apply_service import ApplyService, PlanApplyError
from backend.app.services.planning_service import NoMatchedItemsError
from backend.app.services.scanner_service import ScannerService
from backend.app.services.tv_analysis_service import TvAnalysisService
from backend.app.services.tv_planning_service import TvPlanningService
from backend.app.repositories.plan_operation_repository import PlanOperationRepository
from backend.app.schemas.tv import TvReviewDecisionRequest
from backend.tests.fakes import FakeTmdbClient


@pytest.mark.asyncio
async def test_tv_only_folder_routes_to_tv_pipeline_without_movie_items(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "Show A" / "Season 01").mkdir(parents=True)
    (source / "Show B" / "Season 01").mkdir(parents=True)
    target.mkdir()
    (source / "Show A" / "Season 01" / "Show A S01E01.mkv").write_text("video")
    (source / "Show A" / "Season 01" / "Show A S01E02.mkv").write_text("video")
    (source / "Show B" / "Season 01" / "Show B S01E01.mkv").write_text("video")
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)
    await ScannerService(db_session).discover(scan_session.id)

    classification = await MediaClassificationService(db_session).classify(scan_session.id)
    await ParserService(db_session).parse_scan_session(scan_session.id)
    items = await MediaItemRepository(db_session).list_by_scan_session(scan_session.id)

    class RoutingTmdb(FakeTmdbClient):
        async def search_tv(self, query: str, year: int | None = None, language: str = "ru-RU"):
            self.tv_calls.append((query, year, language))
            if "Show A" in query:
                return [TmdbSearchResult(tmdb_id=101, media_type="tv", title="Show A", year=2024)]
            if "Show B" in query:
                return [TmdbSearchResult(tmdb_id=202, media_type="tv", title="Show B", year=2024)]
            return []

    tmdb = RoutingTmdb(
        tv_details={
            101: TmdbDetailsResult(tmdb_id=101, media_type="tv", title="Show A", year=2024),
            202: TmdbDetailsResult(tmdb_id=202, media_type="tv", title="Show B", year=2024),
        }
    )
    result = await TvAnalysisService(db_session, tmdb_client=tmdb).analyze_scan_session(scan_session.id)
    shows = await TvAnalysisService(db_session, tmdb_client=tmdb).list_shows(scan_session.id)
    for show in shows:
        show.review_decision = ReviewDecision.APPROVED
        show.needs_review = False
    await db_session.commit()
    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)
    tv_payloads = [operation.payload_json or {} for operation in operations]

    assert classification.content_type == "tv"
    assert classification.tv_like_files == 3
    assert len(items) == 0
    assert result.show_count == 2
    assert result.episode_count == 3
    assert {show.title for show in shows} == {"Show A", "Show B"}
    assert {payload.get("tv_show_title") for payload in tv_payloads} == {"Show A", "Show B"}
    assert all(payload.get("media_type") == "tv" for payload in tv_payloads)
    assert all(payload.get("tv_apply_disabled") is True for payload in tv_payloads)
    assert len(tmdb.tv_calls) >= 2
    assert tmdb.movie_calls == []


@pytest.mark.asyncio
async def test_tv_analysis_and_plan_use_direct_target_root(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    season = source / "Тестовый сериал" / "Сезон 1"
    season.mkdir(parents=True)
    target.mkdir()
    (season / "Тестовый сериал S01E01.mkv").write_text("video")
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)
    await ScannerService(db_session).discover(scan_session.id)
    tmdb = FakeTmdbClient(
        tv_results=[
            TmdbSearchResult(
                tmdb_id=123,
                media_type="tv",
                title="Тестовый сериал",
                original_title="Test Show",
                overview="Описание",
                year=2024,
                poster_path="/poster.jpg",
                backdrop_path="/fanart.jpg",
            )
        ],
        tv_details={
            123: TmdbDetailsResult(
                tmdb_id=123,
                media_type="tv",
                title="Тестовый сериал",
                original_title="Test Show",
                overview="Описание",
                year=2024,
                poster_path="/poster.jpg",
                backdrop_path="/fanart.jpg",
                external_ids=TmdbExternalIds(imdb_id="tt1234567", tvdb_id=456, wikidata_id="Q1"),
            )
        },
        tv_season_details={
            (123, 1): TmdbSeasonDetailsResult(
                tmdb_season_id=999,
                season_number=1,
                title="Season 1",
                episodes=[
                    TmdbEpisodeResult(
                        tmdb_episode_id=777,
                        season_number=1,
                        episode_number=1,
                        title="Пилот",
                        overview="Первая серия",
                        air_date="2024-01-01",
                    )
                ],
            )
        },
    )

    result = await TvAnalysisService(db_session, tmdb_client=tmdb).analyze_scan_session(scan_session.id)
    shows = await TvAnalysisService(db_session, tmdb_client=tmdb).list_shows(scan_session.id)
    shows[0].review_decision = ReviewDecision.APPROVED
    shows[0].needs_review = False
    await db_session.commit()
    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)

    assert result.show_count == 1
    assert result.episode_count == 1
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)
    targets = [operation.target_path for operation in operations if operation.target_path]
    payloads = [operation.payload_json or {} for operation in operations]
    episode_payloads = [payload for payload in payloads if payload.get("tv_episode_id")]
    assert any("Тестовый сериал (2024)" in target for target in targets)
    assert all("TV Shows" not in target for target in targets)
    assert any("Season 01" in target for target in targets)
    assert all(payload.get("media_type") == "tv" for payload in payloads)
    assert all(payload.get("tv_apply_disabled") is True for payload in payloads)
    assert {payload.get("tv_show_title") for payload in payloads} == {"Тестовый сериал"}
    assert any(payload.get("season_number") == 1 for payload in payloads)
    assert any(payload.get("episode_number") == 1 for payload in episode_payloads)
    with pytest.raises(PlanApplyError) as exc_info:
        await ApplyService(db_session).apply_plan(plan.id, confirm=True)
    assert exc_info.value.error_code == "tv_apply_disabled"
    assert "Применение сериалов пока отключено" in str(exc_info.value)


@pytest.mark.asyncio
async def test_tv_tmdb_search_uses_ru_first_then_en_fallback(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)

    result = await TvAnalysisService(db_session, tmdb_client=FakeTmdbClient()).analyze_scan_session(scan_session.id)
    assert result.show_count == 0

    from backend.app.models.tv_show import TvShow

    show = TvShow(scan_session_id=scan_session.id, local_group_id="show-1", title="Fallback Show")
    db_session.add(show)
    await db_session.commit()
    await db_session.refresh(show)

    class FallbackTmdb(FakeTmdbClient):
        async def search_tv(self, query: str, year: int | None = None, language: str = "ru-RU"):
            self.tv_calls.append((query, year, language))
            if language == "ru-RU":
                return []
            return [TmdbSearchResult(tmdb_id=321, media_type="tv", title="Fallback Show", year=2024)]

    tmdb = FallbackTmdb()
    results = await TvAnalysisService(db_session, tmdb_client=tmdb).search_show_tmdb(show.id, "Fallback Show")

    assert results[0].tmdb_id == 321
    assert tmdb.tv_calls == [("Fallback Show", None, "ru-RU"), ("Fallback Show", None, "en-US")]
    assert tmdb.movie_calls == []


@pytest.mark.asyncio
async def test_ignored_and_deferred_tv_shows_are_excluded_from_plan(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.commit()
    await db_session.refresh(scan_session)

    from backend.app.models.tv_show import TvShow

    db_session.add_all(
        [
            TvShow(scan_session_id=scan_session.id, local_group_id="ignored", title="Ignored", review_decision=ReviewDecision.IGNORED),
            TvShow(scan_session_id=scan_session.id, local_group_id="deferred", title="Deferred", review_decision=ReviewDecision.DEFERRED),
        ]
    )
    await db_session.commit()

    with pytest.raises(NoMatchedItemsError, match="Нет сериалов для добавления"):
        await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)


@pytest.mark.asyncio
async def test_tv_review_decisions_control_plan_inclusion(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    video = source / "Show A S01E01.mkv"
    video.write_text("video")
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.flush()
    media_file = MediaFile(
        scan_session_id=scan_session.id,
        path=str(video),
        file_name=video.name,
        extension=".mkv",
        kind=MediaFileKind.VIDEO,
        is_video=True,
        size_bytes=5,
    )
    db_session.add(media_file)
    await db_session.flush()
    show = TvShow(scan_session_id=scan_session.id, local_group_id="show-a", title="Show A", year=2024, review_decision=ReviewDecision.PENDING, needs_review=True)
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    db_session.add(
        TvEpisode(
            show_id=show.id,
            season_id=season.id,
            source_file_id=media_file.id,
            season_number=1,
            episode_number=1,
            source_path=str(video),
            needs_review=False,
        )
    )
    await db_session.commit()

    service = TvAnalysisService(db_session)
    confirmed = await service.apply_review_decision(show.id, TvReviewDecisionRequest(decision="approved"))
    assert confirmed.review_decision == ReviewDecision.APPROVED
    assert confirmed.needs_review is False
    plan = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)
    assert any((operation.payload_json or {}).get("tv_show_title") == "Show A" for operation in operations)

    ignored = await service.apply_review_decision(show.id, TvReviewDecisionRequest(decision="ignored"))
    assert ignored.review_decision == ReviewDecision.IGNORED
    with pytest.raises(NoMatchedItemsError, match="Нет сериалов для добавления"):
        await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)

    deferred = await service.apply_review_decision(show.id, TvReviewDecisionRequest(decision="deferred"))
    assert deferred.review_decision == ReviewDecision.DEFERRED
    with pytest.raises(NoMatchedItemsError, match="Нет сериалов для добавления"):
        await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)

    returned = await service.apply_review_decision(show.id, TvReviewDecisionRequest(decision="approved"))
    assert returned.review_decision == ReviewDecision.APPROVED
    rebuilt = await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)
    assert rebuilt.status == "READY"


@pytest.mark.asyncio
async def test_tv_manual_override_by_ids_updates_show_and_preserves_episode_mapping(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    video = source / "Wrong Show S01E01.mkv"
    video.write_text("video")
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.flush()
    media_file = MediaFile(
        scan_session_id=scan_session.id,
        path=str(video),
        file_name=video.name,
        extension=".mkv",
        kind=MediaFileKind.VIDEO,
        is_video=True,
        size_bytes=5,
    )
    db_session.add(media_file)
    await db_session.flush()
    show = TvShow(scan_session_id=scan_session.id, local_group_id="show-a", title="Wrong Show", review_decision=ReviewDecision.PENDING, needs_review=True)
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1, title="Season 01")
    db_session.add(season)
    await db_session.flush()
    episode = TvEpisode(
        show_id=show.id,
        season_id=season.id,
        source_file_id=media_file.id,
        season_number=1,
        episode_number=1,
        source_path=str(video),
        needs_review=False,
    )
    db_session.add(episode)
    await db_session.commit()

    tmdb = FakeTmdbClient(
        tv_details={
            777: TmdbDetailsResult(
                tmdb_id=777,
                media_type="tv",
                title="Correct Show",
                year=2022,
                poster_path="/poster.jpg",
                external_ids=TmdbExternalIds(imdb_id="tt7654321", tvdb_id=987),
            )
        },
        find_results={
            ("tt7654321", "imdb_id"): [TmdbSearchResult(tmdb_id=777, media_type="tv", title="Correct Show", year=2022)],
            ("987", "tvdb_id"): [TmdbSearchResult(tmdb_id=777, media_type="tv", title="Correct Show", year=2022)],
        },
        tv_season_details={
            (777, 1): TmdbSeasonDetailsResult(
                tmdb_season_id=111,
                season_number=1,
                episodes=[TmdbEpisodeResult(tmdb_episode_id=222, season_number=1, episode_number=1, title="Pilot")],
            )
        },
    )
    service = TvAnalysisService(db_session, tmdb_client=tmdb)

    searched = await service.search_show_tmdb(show.id, "Correct Show")
    assert searched == []
    assert tmdb.movie_calls == []
    updated_by_tmdb = await service.lookup_show_tmdb(show.id, tmdb_id=777, select=True)
    assert updated_by_tmdb.review_decision == ReviewDecision.MANUAL_OVERRIDE
    assert updated_by_tmdb.match_source == "manual_tmdb_id"
    updated = await service.lookup_show_tmdb(show.id, imdb_id="tt7654321", select=True)

    assert updated.review_decision == ReviewDecision.MANUAL_OVERRIDE
    assert updated.needs_review is False
    assert updated.title == "Correct Show"
    assert updated.tmdb_id == 777
    assert updated.imdb_id == "tt7654321"
    assert updated.tvdb_id == 987
    assert updated.match_source == "manual_imdb_id"
    refreshed_episode = (await service.tv.list_episodes(updated.id))[0]
    assert refreshed_episode.source_file_id == media_file.id
    assert refreshed_episode.source_path == str(video)
    assert refreshed_episode.tmdb_episode_id == 222
    assert refreshed_episode.title == "Pilot"

    updated_by_tvdb = await service.lookup_show_tmdb(show.id, tvdb_id=987, select=True)
    assert updated_by_tvdb.review_decision == ReviewDecision.MANUAL_OVERRIDE
    assert ("987", "tvdb_id", "ru-RU") in tmdb.find_calls


@pytest.mark.asyncio
async def test_tv_lookup_failure_does_not_corrupt_show(db_session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    scan_session = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan_session)
    await db_session.flush()
    show = TvShow(scan_session_id=scan_session.id, local_group_id="show-a", title="Original Show", tmdb_id=123)
    db_session.add(show)
    await db_session.commit()

    with pytest.raises(LookupError, match="Сериал не найден"):
        await TvAnalysisService(db_session, tmdb_client=FakeTmdbClient()).lookup_show_tmdb(show.id, imdb_id="tt0000000", select=True)

    refreshed = await TvAnalysisService(db_session).get_show(show.id)
    assert refreshed.title == "Original Show"
    assert refreshed.tmdb_id == 123
