from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.scan_sessions import get_gemini_title_normalizer, get_local_title_normalizer, get_tmdb_client
from backend.app.main import app
from backend.app.models.enums import MediaItemStatus, MediaType
from backend.app.models.media_file import MediaFile
from backend.app.models.media_item import MediaItem
from backend.app.models.processed_media_record import ProcessedMediaRecord
from backend.app.models.recognition_memory import RecognitionCorrection
from backend.app.models.tmdb_match_candidate import TmdbMatchCandidate
from backend.app.repositories.media_file_repository import MediaFileRepository
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.repositories.processed_media_repository import ProcessedMediaRepository
from backend.app.repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from backend.app.schemas.recognition import NormalizedTitle, RecognitionCorrectionCreate
from backend.app.schemas.tmdb import TmdbDetailsResult, TmdbExternalIds, TmdbSearchResult
from backend.app.services.parser_service import ParserService
from backend.app.services.processed_media_service import ProcessedMediaService
from backend.app.services.recognition_service import RecognitionService
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.scanner_service import ScannerService
from backend.app.services.tmdb_client import EN_LANGUAGE, RU_LANGUAGE, fetch_localized_details
from backend.app.services.tmdb_service import TMDBService
from backend.app.utils.file_identity import build_file_identity_key
from backend.tests.fakes import FakeTitleNormalizer, FakeTmdbClient


def _movie_result(tmdb_id: int = 603, title: str = "The Matrix") -> TmdbSearchResult:
    return TmdbSearchResult(
        tmdb_id=tmdb_id,
        media_type="movie",
        title=title,
        original_title="The Matrix",
        overview="Русское описание",
        year=1999,
        poster_path="/matrix-poster.jpg",
        backdrop_path="/matrix-backdrop.jpg",
        vote_average=8.7,
        popularity=100,
    )


def _fake_tmdb() -> FakeTmdbClient:
    return FakeTmdbClient(
        movie_results=[_movie_result()],
        movie_details={
            603: TmdbDetailsResult(
                tmdb_id=603,
                media_type="movie",
                title="Матрица",
                original_title="The Matrix",
                overview="Русское описание",
                year=1999,
                poster_path="/matrix-poster.jpg",
                backdrop_path="/matrix-backdrop.jpg",
                external_ids=TmdbExternalIds(imdb_id="tt0133093", wikidata_id="Q83495"),
                metadata_language=RU_LANGUAGE,
            )
        },
    )


async def _match_movie_session(db_session: AsyncSession, tmp_path, fake_client: FakeTmdbClient) -> tuple[int, MediaItem]:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    video = source_path / "The.Matrix.1999.mkv"
    video.write_bytes(b"movie")

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    await ScannerService(db_session).discover(scan_session.id)
    await ParserService(db_session).parse_scan_session(scan_session.id)
    await RecognitionService(
        db_session,
        local_client=FakeTitleNormalizer(
            NormalizedTitle(clean_title="The Matrix", year=1999, media_type="MOVIE", tmdb_queries=["The Matrix 1999"])
        ),
    ).normalize_scan_session(scan_session.id)
    await TMDBService(db_session, client=fake_client).match_scan_session(scan_session.id)
    item = (await MediaItemRepository(db_session).list_by_scan_session(scan_session.id))[0]
    return scan_session.id, item


async def test_processed_record_created_after_match(db_session: AsyncSession, tmp_path) -> None:
    _, item = await _match_movie_session(db_session, tmp_path, _fake_tmdb())
    records = (await db_session.execute(select(ProcessedMediaRecord))).scalars().all()

    assert len(records) == 1
    assert records[0].tmdb_id == item.tmdb_id
    assert records[0].imdb_id == "tt0133093"
    assert records[0].localized_title in {"Матрица", "The Matrix"}


async def test_second_session_reuses_unchanged_file(db_session: AsyncSession, tmp_path) -> None:
    fake_client = _fake_tmdb()
    await _match_movie_session(db_session, tmp_path, fake_client)

    target_path = tmp_path / "library2"
    target_path.mkdir()

    second = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "inbox"), str(target_path))
    await ScannerService(db_session).discover(second.id)
    await ParserService(db_session).parse_scan_session(second.id)
    item = (await MediaItemRepository(db_session).list_by_scan_session(second.id))[0]

    assert item.reused_from_memory is True
    assert item.tmdb_id == 603
    assert item.localized_title in {"Матрица", "The Matrix"}


async def test_reused_item_skips_local_ai(db_session: AsyncSession, tmp_path) -> None:
    fake_client = _fake_tmdb()
    await _match_movie_session(db_session, tmp_path, fake_client)

    second = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "inbox"), str(tmp_path / "library2"))
    await ScannerService(db_session).discover(second.id)
    await ParserService(db_session).parse_scan_session(second.id)
    fake_ai = FakeTitleNormalizer(NormalizedTitle(clean_title="Changed", year=2000, media_type="MOVIE"))

    result = await RecognitionService(db_session, local_client=fake_ai).normalize_scan_session(second.id)
    item = (await MediaItemRepository(db_session).list_by_scan_session(second.id))[0]

    assert result.skipped_count == 1
    assert result.normalized_count == 0
    assert fake_ai.calls == []
    assert item.local_ai_status == "skipped"


async def test_reused_item_skips_gemini(db_session: AsyncSession, tmp_path) -> None:
    fake_client = _fake_tmdb()
    await _match_movie_session(db_session, tmp_path, fake_client)

    second = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "inbox"), str(tmp_path / "library2"))
    await ScannerService(db_session).discover(second.id)
    await ParserService(db_session).parse_scan_session(second.id)
    fake_gemini = FakeTitleNormalizer(NormalizedTitle(clean_title="Changed", year=2000, media_type="MOVIE"))

    result = await RecognitionService(db_session, gemini_client=fake_gemini).resolve_with_gemini(second.id)
    item = (await MediaItemRepository(db_session).list_by_scan_session(second.id))[0]

    assert result.skipped_count == 1
    assert fake_gemini.calls == []
    assert item.gemini_status == "skipped"


async def test_reused_item_skips_tmdb_without_force(db_session: AsyncSession, tmp_path) -> None:
    fake_client = _fake_tmdb()
    await _match_movie_session(db_session, tmp_path, fake_client)

    second = await ScanSessionService(db_session).create_scan_session(str(tmp_path / "inbox"), str(tmp_path / "library2"))
    await ScannerService(db_session).discover(second.id)
    await ParserService(db_session).parse_scan_session(second.id)
    fake_client.movie_calls.clear()
    fake_client.tv_calls.clear()

    result = await TMDBService(db_session, client=fake_client).match_scan_session(second.id)

    assert result.skipped_count == 1
    assert fake_client.movie_calls == []
    assert fake_client.tv_calls == []


async def test_modified_file_is_not_reused(db_session: AsyncSession, tmp_path) -> None:
    fake_client = _fake_tmdb()
    await _match_movie_session(db_session, tmp_path, fake_client)

    source_path = tmp_path / "inbox2"
    source_path.mkdir()
    target_path = tmp_path / "library2"
    target_path.mkdir()
    (source_path / "The.Matrix.1999.mkv").write_bytes(b"changed movie content")

    second = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    await ScannerService(db_session).discover(second.id)
    await ParserService(db_session).parse_scan_session(second.id)
    item = (await MediaItemRepository(db_session).list_by_scan_session(second.id))[0]

    assert item.reused_from_memory is False
    assert item.memory_status == "new"


async def test_delete_session_does_not_delete_processed_record(db_session: AsyncSession, tmp_path) -> None:
    session_id, _ = await _match_movie_session(db_session, tmp_path, _fake_tmdb())
    await ScanSessionService(db_session).delete_scan_session(session_id)

    count = await db_session.scalar(select(func.count()).select_from(ProcessedMediaRecord))
    assert count == 1


async def test_tmdb_search_uses_ru_language(db_session: AsyncSession, tmp_path) -> None:
    fake_client = _fake_tmdb()
    await _match_movie_session(db_session, tmp_path, fake_client)

    assert fake_client.movie_calls[0][2] == RU_LANGUAGE


async def test_tmdb_details_use_ru_language(db_session: AsyncSession, tmp_path) -> None:
    fake_client = _fake_tmdb()
    await _match_movie_session(db_session, tmp_path, fake_client)

    assert ("ru-RU" in call[1] for call in fake_client.movie_detail_calls)


async def test_tmdb_fallback_to_en_when_ru_missing() -> None:
    class RuEmptyClient(FakeTmdbClient):
        async def get_movie_details(self, tmdb_id: int, language: str = RU_LANGUAGE):
            if language == RU_LANGUAGE:
                return TmdbDetailsResult(
                    tmdb_id=tmdb_id,
                    media_type="movie",
                    title="",
                    overview="",
                    metadata_language=RU_LANGUAGE,
                )
            return TmdbDetailsResult(
                tmdb_id=tmdb_id,
                media_type="movie",
                title="The Matrix",
                overview="English overview",
                metadata_language=EN_LANGUAGE,
            )

    details = await fetch_localized_details(RuEmptyClient(), tmdb_id=603, media_type="movie")

    assert details.title == "The Matrix"
    assert details.overview == "English overview"
    assert details.overview_is_fallback is True


async def test_external_ids_saved_on_item_and_candidate(db_session: AsyncSession, tmp_path) -> None:
    _, item = await _match_movie_session(db_session, tmp_path, _fake_tmdb())
    candidate = (await TmdbMatchCandidateRepository(db_session).list_by_media_item(item.id))[0]

    assert item.imdb_id == "tt0133093"
    assert item.wikidata_id == "Q83495"
    assert candidate.imdb_id == "tt0133093"
    assert candidate.poster_url is not None


def test_candidates_endpoint_returns_visual_metadata(client: TestClient, tmp_path) -> None:
    fake_client = _fake_tmdb()
    app.dependency_overrides[get_tmdb_client] = lambda: fake_client
    app.dependency_overrides[get_local_title_normalizer] = lambda: FakeTitleNormalizer()
    app.dependency_overrides[get_gemini_title_normalizer] = lambda: FakeTitleNormalizer()

    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "The.Matrix.1999.mkv").write_bytes(b"movie")

    session_id = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    ).json()["id"]
    client.post(f"/scan-sessions/{session_id}/discover")
    client.post(f"/scan-sessions/{session_id}/parse")
    client.post(f"/scan-sessions/{session_id}/normalize-local-ai")
    client.post(f"/scan-sessions/{session_id}/match-tmdb")
    item_id = client.get(f"/scan-sessions/{session_id}/items").json()[0]["id"]

    response = client.get(f"/items/{item_id}/tmdb-candidates")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    assert payload[0]["poster_url"]
    assert payload[0]["imdb_id"] == "tt0133093"
    assert payload[0]["metadata_language"] == RU_LANGUAGE

    app.dependency_overrides.pop(get_tmdb_client, None)
    app.dependency_overrides.pop(get_local_title_normalizer, None)
    app.dependency_overrides.pop(get_gemini_title_normalizer, None)


async def test_selected_candidate_remains_after_match(db_session: AsyncSession, tmp_path) -> None:
    _, item = await _match_movie_session(db_session, tmp_path, _fake_tmdb())
    candidates = await TmdbMatchCandidateRepository(db_session).list_by_media_item(item.id)

    assert len(candidates) >= 1
    assert any(candidate.is_selected for candidate in candidates)


async def test_candidate_selection_updates_external_ids(db_session: AsyncSession, tmp_path) -> None:
    fake_client = _fake_tmdb()
    session_id, item = await _match_movie_session(db_session, tmp_path, fake_client)
    candidates = await TmdbMatchCandidateRepository(db_session).list_by_media_item(item.id)
    second = candidates[1] if len(candidates) > 1 else candidates[0]

    await TMDBService(db_session, client=fake_client).select_candidate(item.id, second.id)
    refreshed = await MediaItemRepository(db_session).get_by_id(item.id)

    assert refreshed is not None
    assert refreshed.imdb_id == "tt0133093"
    assert refreshed.localized_title in {"Матрица", "The Matrix"}
