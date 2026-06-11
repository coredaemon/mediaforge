from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaItemStatus, MediaType
from backend.app.models.media_item import MediaItem
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.repositories.app_settings_repository import AppSettingsRepository
from backend.app.repositories.recognition_memory_repository import RecognitionMemoryRepository
from backend.app.schemas.recognition import NormalizedTitle, RecognitionCorrectionCreate
from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.services.recognition_clients import _parse_normalized_json
from backend.app.services.recognition_service import RecognitionService
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.tmdb_service import TMDBService
from backend.tests.fakes import FakeTitleNormalizer, FakeTmdbClient


class FakeRawJsonNormalizer:
    def __init__(self, json_body: str) -> None:
        self.json_body = json_body
        self.model = "fake-raw"

    async def normalize(self, original_name: str, parser_title: str | None, parser_year: int | None):
        return _parse_normalized_json(
            self.json_body,
            parser_title=parser_title,
            parser_year=parser_year,
        )


async def test_manual_correction_saves_memory_and_updates_item(db_session: AsyncSession, tmp_path) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.UNKNOWN,
            status=MediaItemStatus.NEEDS_REVIEW,
            original_title="In.The.Grey2026.AMZN.New.Team.mkv",
            parsed_title="In The Grey2026 AMZN New Team",
            needs_review=True,
        )
    )
    await db_session.commit()

    correction = await RecognitionService(db_session).create_correction(
        item.id,
        RecognitionCorrectionCreate(
            corrected_title="In The Grey",
            corrected_year=2026,
            corrected_media_type="MOVIE",
            removed_tokens=["AMZN", "New", "Team"],
        ),
    )
    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)
    token_rules = await RecognitionMemoryRepository(db_session).list_token_rules()

    assert correction.corrected_title == "In The Grey"
    assert refreshed is not None
    assert refreshed.parsed_title == "In The Grey"
    assert refreshed.year == 2026
    assert refreshed.media_type == MediaType.MOVIE
    assert refreshed.tmdb_queries == ["In The Grey"]
    assert {rule.token for rule in token_rules} == {"amzn", "new", "team"}


async def test_local_ai_normalization_updates_query_fields(db_session: AsyncSession, tmp_path) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.NEEDS_REVIEW,
            original_title="In.The.Grey2026.AMZN.New.Team.mkv",
            parsed_title="In The Grey2026 AMZN New Team",
            needs_review=True,
        )
    )
    await db_session.commit()
    fake_ai = FakeTitleNormalizer(
        NormalizedTitle(
            clean_title="In The Grey",
            year=2026,
            media_type="MOVIE",
            confidence=0.94,
            junk_tokens=["AMZN", "New", "Team"],
            tmdb_queries=["In The Grey"],
        )
    )

    result = await RecognitionService(db_session, local_client=fake_ai).normalize_scan_session(scan_session.id)
    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)

    assert result.normalized_count == 1
    assert refreshed is not None
    assert refreshed.ai_clean_title == "In The Grey"
    assert refreshed.ai_year == 2026
    assert refreshed.ai_junk_tokens == ["AMZN", "New", "Team"]
    assert refreshed.local_ai_status == "success"
    assert refreshed.local_ai_duration_ms is not None
    assert refreshed.local_ai_response_valid_json is True
    assert refreshed.local_ai_model == "fake-model"
    assert refreshed.tmdb_queries == [
        "In The Grey",
        "In The Grey2026 AMZN New Team",
        "In.The.Grey2026.AMZN.New.Team.mkv",
    ]


async def test_gemini_failure_is_counted_without_breaking_pipeline(db_session: AsyncSession, tmp_path) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.UNMATCHED,
            original_title="Unknown.2026.mkv",
            parsed_title="Unknown",
            needs_review=True,
        )
    )
    await db_session.commit()

    result = await RecognitionService(db_session, gemini_client=FakeTitleNormalizer(fail=True)).resolve_with_gemini(
        scan_session.id
    )
    item = (await MediaItemRepository(db_session).list_by_scan_session(scan_session.id))[0]

    assert result.normalized_count == 0
    assert result.error_count == 1
    assert item.gemini_status == "failed"
    assert item.gemini_error == "normalizer failed"


async def test_preflight_success_with_fake_local_and_cloud_clients(db_session: AsyncSession) -> None:
    result = await RecognitionService(
        db_session,
        local_client=FakeTitleNormalizer(),
        gemini_client=FakeTitleNormalizer(),
    ).preflight()

    assert result.ok
    assert result.local.duration_ms == 7
    assert result.cloud.duration_ms == 7
    assert result.local.response_valid_json
    assert result.cloud.response_valid_json


async def test_preflight_fails_if_local_connection_fails(db_session: AsyncSession) -> None:
    result = await RecognitionService(
        db_session,
        local_client=FakeTitleNormalizer(fail=True),
        gemini_client=FakeTitleNormalizer(),
    ).preflight()

    assert not result.ok
    assert not result.local.ok
    assert result.local.error_type == "ConnectError"


async def test_preflight_fails_if_local_returns_invalid_json(db_session: AsyncSession) -> None:
    result = await RecognitionService(
        db_session,
        local_client=FakeTitleNormalizer(preflight_valid_json=False),
        gemini_client=FakeTitleNormalizer(),
    ).preflight()

    assert not result.ok
    assert not result.local.response_valid_json


async def test_preflight_fails_if_cloud_connection_fails(db_session: AsyncSession) -> None:
    result = await RecognitionService(
        db_session,
        local_client=FakeTitleNormalizer(),
        gemini_client=FakeTitleNormalizer(fail=True),
    ).preflight()

    assert not result.ok
    assert not result.cloud.ok
    assert result.cloud.error_type == "ConnectError"


async def test_preflight_fails_if_cloud_returns_invalid_json(db_session: AsyncSession) -> None:
    result = await RecognitionService(
        db_session,
        local_client=FakeTitleNormalizer(),
        gemini_client=FakeTitleNormalizer(preflight_valid_json=False),
    ).preflight()

    assert not result.ok
    assert not result.cloud.response_valid_json


async def test_preflight_does_not_expose_saved_api_keys(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update(
        {
            "ai_provider": "ollama",
            "ai_model": "gemma",
            "cloud_ai_provider": "gemini",
            "cloud_ai_api_key": "fake-cloud-key-that-must-not-leak",
            "cloud_ai_model": "gemini-test",
        }
    )
    await db_session.commit()

    result = await RecognitionService(
        db_session,
        local_client=FakeTitleNormalizer(),
        gemini_client=FakeTitleNormalizer(),
    ).preflight()
    serialized = result.model_dump_json()

    assert "fake-cloud-key-that-must-not-leak" not in serialized


async def test_malformed_tmdb_queries_are_normalized_and_used_for_tmdb(db_session: AsyncSession, tmp_path) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.NEEDS_REVIEW,
            original_title="In.The.Grey2026.1080p.AMZN-New-Team.mkv",
            parsed_title="In The Grey2026 AMZN New Team",
            year=2026,
            needs_review=True,
        )
    )
    await db_session.commit()
    raw_json = """
    {
      "clean_title": "In the Grey",
      "year": 2026,
      "media_type": "movie",
      "confidence": 0.82,
      "junk_tokens": ["AMZN", "New Team"],
      "tmdb_queries": [
        {"query": "In the Grey", "year": 2026},
        {"query": "In the Grey", "type": "movie"}
      ],
      "explanation": "Removed release tags."
    }
    """
    fake_ai = FakeRawJsonNormalizer(raw_json)

    normalize_result = await RecognitionService(db_session, local_client=fake_ai).normalize_scan_session(
        scan_session.id
    )
    item = (await MediaItemRepository(db_session).list_by_scan_session(scan_session.id))[0]

    assert normalize_result.normalized_count == 1
    assert normalize_result.error_count == 0
    assert item.local_ai_status == "success"
    assert item.ai_clean_title == "In the Grey"
    assert "In the Grey 2026" in item.tmdb_queries
    assert "In the Grey" in item.tmdb_queries
    assert item.local_ai_error is not None
    assert "tmdb_queries format auto-normalized" in item.local_ai_error

    fake_tmdb = FakeTmdbClient(
        movie_results=[TmdbSearchResult(tmdb_id=100, media_type="movie", title="In The Grey", year=2026)]
    )
    match_result = await TMDBService(db_session, client=fake_tmdb).match_scan_session(scan_session.id)

    assert len(fake_tmdb.movie_calls) >= 1
    assert fake_tmdb.movie_calls[0][0] in {"In the Grey", "In the Grey 2026"}
    assert match_result.matched_count + match_result.needs_review_count >= 1


async def test_tmdb_uses_ai_query_before_parser_title(db_session: AsyncSession, tmp_path) -> None:
    scan_session = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "in"), str(tmp_path / "out"))
    await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan_session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.NEEDS_REVIEW,
            parsed_title="In The Grey2026 AMZN New Team",
            year=2026,
            ai_clean_title="In The Grey",
            ai_year=2026,
            tmdb_queries=["In The Grey"],
            needs_review=True,
        )
    )
    await db_session.commit()
    fake_tmdb = FakeTmdbClient(
        movie_results=[TmdbSearchResult(tmdb_id=100, media_type="movie", title="In The Grey", year=2026)]
    )

    result = await TMDBService(db_session, client=fake_tmdb).match_scan_session(scan_session.id)

    assert result.matched_count == 1
    assert fake_tmdb.movie_calls[0] == ("In The Grey", 2026, "ru-RU")
