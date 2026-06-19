from pathlib import Path

import pytest

from backend.app.models.enums import ReviewDecision
from backend.app.models.scan_session import ScanSession
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.services.media_classification_service import MediaClassificationService
from backend.app.services.parser_service import ParserService
from backend.app.schemas.tmdb import TmdbDetailsResult, TmdbEpisodeResult, TmdbExternalIds, TmdbSearchResult, TmdbSeasonDetailsResult
from backend.app.services.apply_service import ApplyService, PlanApplyError
from backend.app.services.planning_service import NoMatchedItemsError
from backend.app.services.scanner_service import ScannerService
from backend.app.services.tv_analysis_service import TvAnalysisService
from backend.app.services.tv_planning_service import TvPlanningService
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

    assert classification.content_type == "tv"
    assert classification.tv_like_files == 3
    assert len(items) == 0
    assert result.show_count == 2
    assert result.episode_count == 3
    assert {show.title for show in shows} == {"Show A", "Show B"}
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
    from backend.app.repositories.plan_operation_repository import PlanOperationRepository

    operations = await PlanOperationRepository(db_session).list_by_plan(plan.id)
    targets = [operation.target_path for operation in operations if operation.target_path]
    assert any("Тестовый сериал (2024)" in target for target in targets)
    assert all("TV Shows" not in target for target in targets)
    assert any("Season 01" in target for target in targets)
    with pytest.raises(PlanApplyError):
        await ApplyService(db_session).apply_plan(plan.id, confirm=True)


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

    with pytest.raises(NoMatchedItemsError):
        await TvPlanningService(db_session).create_plan_for_scan_session(scan_session.id, force=True)
