import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaItemStatus, MediaType, ReviewDecision
from backend.app.models.media_item import MediaItem
from backend.app.repositories.app_settings_repository import AppSettingsRepository
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.repositories.processed_media_repository import ProcessedMediaRepository
from backend.app.schemas.review import ReviewDecisionRequest, TmdbManualLookupRequest, TmdbManualSearchRequest
from backend.app.schemas.settings import AppSettingsUpdate
from backend.app.schemas.tmdb import TmdbDetailsResult, TmdbExternalIds, TmdbSearchResult
from backend.app.services.item_review_service import ItemReviewService
from backend.app.services.planning_service import NoMatchedItemsError, PlanningService
from backend.app.services.recognition_service import RecognitionService
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.settings_service import SettingsService
from backend.app.services.tmdb_service import TMDBService, TmdbLookupNotFoundError
from backend.tests.fakes import FakeTitleNormalizer, FakeTmdbClient


async def _create_movie_item(db_session: AsyncSession, tmp_path) -> MediaItem:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.NEEDS_REVIEW,
            parsed_title="Отец",
            year=2026,
            needs_review=True,
        )
    )
    await db_session.commit()
    return item


def _movie_client() -> FakeTmdbClient:
    return FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(
                tmdb_id=123456,
                media_type="movie",
                title="Отец",
                year=2026,
                poster_path="/otets.jpg",
            )
        ],
        movie_details={
            123456: TmdbDetailsResult(
                tmdb_id=123456,
                media_type="movie",
                title="Отец",
                original_title="Father",
                overview="Русское описание",
                year=2026,
                poster_path="/otets.jpg",
                external_ids=TmdbExternalIds(imdb_id="tt1234567", wikidata_id="Q1"),
                metadata_language="ru-RU",
            )
        },
        find_results={
            ("tt1234567", "imdb_id"): [
                TmdbSearchResult(tmdb_id=123456, media_type="movie", title="Отец", year=2026)
            ],
            ("42", "tvdb_id"): [
                TmdbSearchResult(tmdb_id=9001, media_type="tv", title="Сериал", year=2020)
            ],
        },
        tv_details={
            9001: TmdbDetailsResult(
                tmdb_id=9001,
                media_type="tv",
                title="Сериал",
                overview="Описание",
                year=2020,
                external_ids=TmdbExternalIds(imdb_id="tt999", tvdb_id=42),
                metadata_language="ru-RU",
            )
        },
    )


async def test_manual_search_returns_candidates(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    client = _movie_client()
    results = await TMDBService(db_session, client=client).manual_search(item.id, "Отец", 2026, "movie")
    assert len(results) == 1
    assert results[0].title == "Отец"


async def test_manual_search_uses_ru_then_en_fallback(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    client = FakeTmdbClient(movie_results=[])
    service = TMDBService(db_session, client=client)

    async def search_movie(query: str, year: int | None = None, language: str = "ru-RU"):
        client.movie_calls.append((query, year, language))
        if language == "en-US":
            return [TmdbSearchResult(tmdb_id=1, media_type="movie", title="Father", year=2026)]
        return []

    client.search_movie = search_movie  # type: ignore[method-assign]
    results = await service.manual_search(item.id, "Отец", 2026, "movie")
    assert [call[2] for call in client.movie_calls] == ["ru-RU", "en-US"]
    assert results[0].title == "Father"


async def test_lookup_by_tmdb_movie_id(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    candidate = await TMDBService(db_session, client=_movie_client()).manual_lookup(
        item.id, tmdb_id=123456, media_type="movie"
    )
    assert candidate.tmdb_id == 123456
    assert candidate.title == "Отец"


async def test_lookup_by_imdb_id(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    client = _movie_client()
    candidate = await TMDBService(db_session, client=client).manual_lookup(item.id, imdb_id="tt1234567")
    assert candidate.tmdb_id == 123456
    assert ("tt1234567", "imdb_id", "ru-RU") in client.find_calls


async def test_lookup_by_tvdb_id(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    client = _movie_client()
    candidate = await TMDBService(db_session, client=client).manual_lookup(item.id, tvdb_id=42, media_type="tv")
    assert candidate.tmdb_id == 9001
    assert candidate.media_type == "tv"


async def test_lookup_not_found_raises(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    with pytest.raises(TmdbLookupNotFoundError):
        await TMDBService(db_session, client=FakeTmdbClient()).manual_lookup(item.id, imdb_id="tt0000000")


async def test_approve_item(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    item.status = MediaItemStatus.MATCHED
    item.tmdb_id = 123456
    await db_session.commit()
    updated = await ItemReviewService(db_session).apply_review_decision(
        item.id,
        ReviewDecisionRequest(decision=ReviewDecision.APPROVED, note="Правильный фильм"),
    )
    assert updated.review_decision == ReviewDecision.APPROVED
    assert updated.review_note == "Правильный фильм"


async def test_ignore_item(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    updated = await ItemReviewService(db_session).apply_review_decision(
        item.id,
        ReviewDecisionRequest(decision=ReviewDecision.IGNORED, note="Не добавлять"),
    )
    assert updated.review_decision == ReviewDecision.IGNORED
    assert updated.status == MediaItemStatus.IGNORED


async def test_defer_item(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    updated = await ItemReviewService(db_session).apply_review_decision(
        item.id,
        ReviewDecisionRequest(decision=ReviewDecision.DEFERRED),
    )
    assert updated.review_decision == ReviewDecision.DEFERRED


async def test_manual_override_with_tmdb_id(db_session: AsyncSession, tmp_path) -> None:
    item = await _create_movie_item(db_session, tmp_path)
    updated = await ItemReviewService(db_session, TMDBService(db_session, client=_movie_client())).apply_review_decision(
        item.id,
        ReviewDecisionRequest(
            decision=ReviewDecision.MANUAL_OVERRIDE,
            manual_tmdb_id=123456,
            manual_media_type="movie",
            note="Выбран вручную",
        ),
    )
    assert updated.review_decision == ReviewDecision.MANUAL_OVERRIDE
    assert updated.tmdb_id == 123456
    assert updated.status == MediaItemStatus.MATCHED


async def test_manual_override_updates_processed_media_record(db_session: AsyncSession, tmp_path) -> None:
    from backend.app.models.media_file import MediaFile
    from backend.app.models.enums import MediaFileKind

    item = await _create_movie_item(db_session, tmp_path)
    db_session.add(
        MediaFile(
            scan_session_id=item.scan_session_id,
            media_item_id=item.id,
            path=str(tmp_path / "in" / "movie.mkv"),
            file_name="movie.mkv",
            extension=".mkv",
            size_bytes=100,
            kind=MediaFileKind.VIDEO,
            is_video=True,
            is_subtitle=False,
            is_sidecar=False,
        )
    )
    await db_session.commit()
    await ItemReviewService(db_session, TMDBService(db_session, client=_movie_client())).apply_review_decision(
        item.id,
        ReviewDecisionRequest(
            decision=ReviewDecision.MANUAL_OVERRIDE,
            manual_tmdb_id=123456,
            manual_media_type="movie",
        ),
    )
    from sqlalchemy import select
    from backend.app.models.processed_media_record import ProcessedMediaRecord

    result = await db_session.execute(select(ProcessedMediaRecord))
    records = list(result.scalars().all())
    assert len(records) == 1
    assert records[0].tmdb_id == 123456


async def test_select_candidate_sets_review_decision(db_session: AsyncSession, tmp_path) -> None:
    from backend.app.repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
    from backend.app.models.tmdb_match_candidate import TmdbMatchCandidate

    item = await _create_movie_item(db_session, tmp_path)
    candidate = await TmdbMatchCandidateRepository(db_session).create(
        TmdbMatchCandidate(
            media_item_id=item.id,
            tmdb_id=123456,
            media_type="movie",
            title="Отец",
            year=2026,
            score=1.0,
            is_selected=False,
        )
    )
    await db_session.commit()
    await TMDBService(db_session, client=_movie_client()).select_candidate(item.id, candidate.id)
    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)
    assert refreshed is not None
    assert refreshed.review_decision == ReviewDecision.MANUAL_OVERRIDE


async def _matched_item_with_file(db_session: AsyncSession, tmp_path, review_decision: str) -> int:
    from backend.app.models.media_file import MediaFile
    from backend.app.models.enums import MediaFileKind

    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    (tmp_path / "in").mkdir(parents=True, exist_ok=True)
    (tmp_path / "in" / "movie.mkv").write_bytes(b"x")
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.MATCHED,
            parsed_title="Отец",
            matched_title="Отец",
            matched_year=2026,
            year=2026,
            tmdb_id=123456,
            needs_review=False,
            review_decision=review_decision,
        )
    )
    db_session.add(
        MediaFile(
            scan_session_id=scan_session.id,
            media_item_id=item.id,
            path=str(tmp_path / "in" / "movie.mkv"),
            file_name="movie.mkv",
            extension=".mkv",
            size_bytes=1,
            kind=MediaFileKind.VIDEO,
            is_video=True,
            is_subtitle=False,
            is_sidecar=False,
        )
    )
    await db_session.commit()
    return scan_session.id


async def test_ignored_item_excluded_from_plan(db_session: AsyncSession, tmp_path) -> None:
    session_id = await _matched_item_with_file(db_session, tmp_path, ReviewDecision.IGNORED)
    with pytest.raises(NoMatchedItemsError):
        await PlanningService(db_session).create_plan_for_scan_session(session_id)


async def test_deferred_item_excluded_from_plan(db_session: AsyncSession, tmp_path) -> None:
    session_id = await _matched_item_with_file(db_session, tmp_path, ReviewDecision.DEFERRED)
    with pytest.raises(NoMatchedItemsError):
        await PlanningService(db_session).create_plan_for_scan_session(session_id)


async def test_manual_override_included_in_plan(db_session: AsyncSession, tmp_path) -> None:
    session_id = await _matched_item_with_file(db_session, tmp_path, ReviewDecision.MANUAL_OVERRIDE)
    plan = await PlanningService(db_session).create_plan_for_scan_session(session_id)
    assert plan.id > 0


async def test_approved_item_included_in_plan(db_session: AsyncSession, tmp_path) -> None:
    session_id = await _matched_item_with_file(db_session, tmp_path, ReviewDecision.APPROVED)
    plan = await PlanningService(db_session).create_plan_for_scan_session(session_id)
    assert plan.id > 0


async def test_primary_cloud_failure_uses_fallback(db_session: AsyncSession) -> None:
    primary = FakeTitleNormalizer(fail=True)
    fallback = FakeTitleNormalizer(result=FakeTitleNormalizer().result)
    fallback.model = "fallback-model"
    service = RecognitionService(db_session, gemini_client=primary)
    await AppSettingsRepository(db_session).update(
        {
            "cloud_ai_provider": "gemini",
            "cloud_ai_api_key": "primary-key",
            "cloud_ai_model": "primary-model",
            "cloud_ai_fallback_provider": "gemini",
            "cloud_ai_fallback_model": "fallback-model",
        }
    )
    await db_session.commit()

    scan_session = await ScanSessionService(db_session).create_scan_session("/in", "/out")
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.NEEDS_REVIEW,
            original_title="Bad.Name.2026.mkv",
            parsed_title="Bad Name",
            year=2026,
            needs_review=True,
        )
    )
    await db_session.commit()

    original_get = RecognitionService._get_client

    fallback_normalizer = fallback

    async def patched_get(self, use_gemini: bool, use_fallback: bool = False):
        if not use_gemini:
            return FakeTitleNormalizer()
        if use_fallback:
            return fallback_normalizer
        return primary

    RecognitionService._get_client = patched_get  # type: ignore[method-assign]
    try:
        result = await service.resolve_with_gemini(scan_session.id)
    finally:
        RecognitionService._get_client = original_get  # type: ignore[method-assign]

    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)
    assert result.normalized_count == 1
    assert refreshed is not None
    assert refreshed.gemini_model == "fallback-model"
    assert "fallback" in (refreshed.gemini_error or "").lower()


async def test_preflight_allows_pipeline_when_fallback_works(db_session: AsyncSession) -> None:
    primary = FakeTitleNormalizer(fail=True)
    fallback = FakeTitleNormalizer()
    service = RecognitionService(db_session, gemini_client=primary)

    fallback_normalizer = fallback

    async def patched_get(self, use_gemini: bool, use_fallback: bool = False):
        if not use_gemini:
            return FakeTitleNormalizer()
        if use_fallback:
            return fallback_normalizer
        return primary

    original_get = RecognitionService._get_client
    RecognitionService._get_client = patched_get  # type: ignore[method-assign]
    try:
        result = await service.preflight()
    finally:
        RecognitionService._get_client = original_get  # type: ignore[method-assign]

    assert result.ok
    assert result.warning is not None
    assert result.cloud_fallback is not None
    assert result.cloud_fallback.ok


async def test_get_settings_does_not_expose_cloud_keys(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update(
        {
            "cloud_ai_provider": "gemini",
            "cloud_ai_api_key": "secret-primary",
            "cloud_ai_model": "gemini-2.0-flash",
            "cloud_ai_fallback_provider": "gemini",
            "cloud_ai_fallback_api_key": "secret-fallback",
            "cloud_ai_fallback_model": "gemini-1.5-flash",
        }
    )
    await db_session.commit()
    result = await SettingsService(db_session).get_settings()
    dumped = result.model_dump()
    assert "secret-primary" not in str(dumped)
    assert "secret-fallback" not in str(dumped)
    assert result.cloud_primary_configured is True
    assert result.cloud_fallback_configured is True


async def test_empty_cloud_key_does_not_overwrite_saved_key(db_session: AsyncSession) -> None:
    await SettingsService(db_session).update_settings(
        AppSettingsUpdate(cloud_ai_api_key="saved-primary", cloud_ai_provider="gemini", cloud_ai_model="m1")
    )
    await SettingsService(db_session).update_settings(AppSettingsUpdate(cloud_ai_api_key=""))
    settings = await AppSettingsRepository(db_session).get_or_create()
    assert settings.cloud_ai_api_key == "saved-primary"
