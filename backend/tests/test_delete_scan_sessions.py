from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.scan_sessions import get_tmdb_client
from backend.app.main import app
from backend.app.models.apply_operation_log import ApplyOperationLog
from backend.app.models.apply_run import ApplyRun
from backend.app.models.enums import MediaFileKind
from backend.app.models.media_file import MediaFile
from backend.app.models.media_item import MediaItem
from backend.app.models.operation_plan import OperationPlan
from backend.app.models.plan_operation import PlanOperation
from backend.app.models.processed_media_record import ProcessedMediaRecord
from backend.app.models.recognition_memory import RecognitionCorrection
from backend.app.models.tmdb_match_candidate import TmdbMatchCandidate
from backend.app.models.tv_episode import TvEpisode
from backend.app.models.tv_grouping_run import TvGroupingRun
from backend.app.models.tv_season import TvSeason
from backend.app.models.tv_show import TvShow
from backend.app.schemas.recognition import RecognitionCorrectionCreate
from backend.app.schemas.review import BulkApproveRequest
from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.services.apply_service import ApplyService
from backend.app.services.bulk_review_service import BulkReviewService
from backend.app.services.recognition_service import RecognitionService
from backend.app.services.scan_session_service import ScanSessionService
from backend.tests.fakes import FakeTmdbClient


async def _seed_full_session(db_session: AsyncSession, tmp_path: Path) -> tuple[int, Path]:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    media_file = source_path / "The.Matrix.1999.mkv"
    media_file.write_bytes(b"movie")

    scan_session = await ScanSessionService(db_session).create_scan_session(str(source_path), str(target_path))
    return scan_session.id, media_file


def test_delete_existing_session_returns_ok(client: TestClient, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]

    delete_response = client.delete(f"/scan-sessions/{session_id}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True, "id": session_id}


def test_delete_missing_session_returns_404(client: TestClient) -> None:
    response = client.delete("/scan-sessions/99999")
    assert response.status_code == 404


async def test_delete_session_cascades_related_rows(db_session: AsyncSession, tmp_path) -> None:
    fake_client = FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(
                tmdb_id=603,
                media_type="movie",
                title="The Matrix",
                year=1999,
                poster_path="/matrix-poster.jpg",
            )
        ]
    )
    app.dependency_overrides[get_tmdb_client] = lambda: fake_client

    session_id, _ = await _seed_full_session(db_session, tmp_path)
    await db_session.commit()

    from backend.app.services.scanner_service import ScannerService
    from backend.app.services.parser_service import ParserService
    from backend.app.services.tmdb_service import TMDBService
    from backend.app.services.planning_service import PlanningService
    from backend.app.repositories.media_item_repository import MediaItemRepository

    await ScannerService(db_session).discover(session_id)
    await ParserService(db_session).parse_scan_session(session_id)
    await TMDBService(db_session, client=fake_client).match_scan_session(session_id)
    await PlanningService(db_session).create_plan_for_scan_session(session_id)

    item = (await MediaItemRepository(db_session).list_by_scan_session(session_id))[0]
    await RecognitionService(db_session).create_correction(
        item.id,
        RecognitionCorrectionCreate(corrected_title="The Matrix", corrected_year=1999),
    )
    await db_session.commit()

    await ScanSessionService(db_session).delete_scan_session(session_id)

    assert await db_session.scalar(select(func.count()).select_from(MediaFile)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MediaItem)) == 0
    assert await db_session.scalar(select(func.count()).select_from(TmdbMatchCandidate)) == 0
    assert await db_session.scalar(select(func.count()).select_from(OperationPlan)) == 0
    assert await db_session.scalar(select(func.count()).select_from(PlanOperation)) == 0
    assert await db_session.scalar(select(func.count()).select_from(RecognitionCorrection)) == 1

    app.dependency_overrides.pop(get_tmdb_client, None)


async def test_delete_session_does_not_remove_files_on_disk(db_session: AsyncSession, tmp_path) -> None:
    session_id, media_file = await _seed_full_session(db_session, tmp_path)
    await db_session.commit()

    await ScanSessionService(db_session).delete_scan_session(session_id)

    assert media_file.exists()


def _mock_http_client() -> httpx.AsyncClient:
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-type": "image/jpeg"}
    response.content = b"poster"
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    client.aclose = AsyncMock()
    return client


async def test_delete_session_after_apply_cascades_apply_tables(db_session: AsyncSession, tmp_path) -> None:
    fake_client = FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(
                tmdb_id=603,
                media_type="movie",
                title="The Matrix",
                year=1999,
                poster_path="/matrix-poster.jpg",
                backdrop_path="/matrix-backdrop.jpg",
            )
        ]
    )
    app.dependency_overrides[get_tmdb_client] = lambda: fake_client

    session_id, media_file = await _seed_full_session(db_session, tmp_path)
    library_path = media_file.parent.parent / "library"
    await db_session.commit()

    from backend.app.repositories.media_item_repository import MediaItemRepository
    from backend.app.services.parser_service import ParserService
    from backend.app.services.planning_service import PlanningService
    from backend.app.services.scanner_service import ScannerService
    from backend.app.services.tmdb_service import TMDBService

    await ScannerService(db_session).discover(session_id)
    await ParserService(db_session).parse_scan_session(session_id)
    await TMDBService(db_session, client=fake_client).match_scan_session(session_id)
    await BulkReviewService(db_session).approve_all(session_id, BulkApproveRequest(scope="matched"))
    plan = await PlanningService(db_session).create_plan_for_scan_session(session_id)
    await ApplyService(db_session, http_client=_mock_http_client()).apply_plan(plan.id, confirm=True)

    processed_before = await db_session.scalar(select(func.count()).select_from(ProcessedMediaRecord))
    assert processed_before and processed_before >= 1
    assert await db_session.scalar(select(func.count()).select_from(ApplyRun)) >= 1
    assert await db_session.scalar(select(func.count()).select_from(ApplyOperationLog)) >= 1

    await ScanSessionService(db_session).delete_scan_session(session_id)

    assert await db_session.scalar(select(func.count()).select_from(MediaFile)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MediaItem)) == 0
    assert await db_session.scalar(select(func.count()).select_from(TmdbMatchCandidate)) == 0
    assert await db_session.scalar(select(func.count()).select_from(OperationPlan)) == 0
    assert await db_session.scalar(select(func.count()).select_from(PlanOperation)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ApplyRun)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ApplyOperationLog)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProcessedMediaRecord)) == processed_before
    library_files = list(library_path.rglob("*.mkv"))
    assert len(library_files) >= 1

    items_after = await MediaItemRepository(db_session).list_by_scan_session(session_id)
    assert len(items_after) == 0

    app.dependency_overrides.pop(get_tmdb_client, None)


async def test_delete_session_after_tv_grouping_cascades_tv_tables(db_session: AsyncSession, tmp_path) -> None:
    session_id, media_file = await _seed_full_session(db_session, tmp_path)
    db_file = MediaFile(
        scan_session_id=session_id,
        path=str(media_file),
        file_name=media_file.name,
        extension=".mkv",
        kind=MediaFileKind.VIDEO,
        is_video=True,
    )
    db_session.add(db_file)
    await db_session.flush()
    show = TvShow(scan_session_id=session_id, local_group_id="show-1", title="Example Show")
    db_session.add(show)
    await db_session.flush()
    season = TvSeason(show_id=show.id, season_number=1)
    db_session.add(season)
    await db_session.flush()
    db_session.add(
        TvEpisode(
            show_id=show.id,
            season_id=season.id,
            source_file_id=db_file.id,
            season_number=1,
            episode_number=1,
            source_path=str(media_file),
            target_path=str(tmp_path / "library" / "Example Show" / "S01E01.mkv"),
        )
    )
    db_session.add(
        TvGroupingRun(
            scan_session_id=session_id,
            show_id=show.id,
            provider="openrouter",
            model="fast/model",
            status="success",
        )
    )
    await db_session.commit()

    await ScanSessionService(db_session).delete_scan_session(session_id)

    assert await db_session.scalar(select(func.count()).select_from(TvEpisode)) == 0
    assert await db_session.scalar(select(func.count()).select_from(TvSeason)) == 0
    assert await db_session.scalar(select(func.count()).select_from(TvGroupingRun)) == 0
    assert await db_session.scalar(select(func.count()).select_from(TvShow)) == 0
    assert media_file.exists()


def test_delete_session_via_api_after_apply(client: TestClient, tmp_path) -> None:
    fake_client = FakeTmdbClient(
        movie_results=[
            TmdbSearchResult(
                tmdb_id=603,
                media_type="movie",
                title="The Matrix",
                year=1999,
                poster_path="/matrix-poster.jpg",
                backdrop_path="/matrix-backdrop.jpg",
            )
        ]
    )
    app.dependency_overrides[get_tmdb_client] = lambda: fake_client

    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()
    (source_path / "The.Matrix.1999.mkv").write_bytes(b"movie")

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]
    client.post(f"/scan-sessions/{session_id}/discover")
    client.post(f"/scan-sessions/{session_id}/parse")
    client.post(f"/scan-sessions/{session_id}/match-tmdb")
    client.post(f"/scan-sessions/{session_id}/review/approve-all", json={"scope": "matched"})
    plan = client.post(f"/scan-sessions/{session_id}/plan").json()
    client.post(f"/operation-plans/{plan['id']}/apply", json={"confirm": True})

    delete_response = client.delete(f"/scan-sessions/{session_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True, "id": session_id}

    app.dependency_overrides.pop(get_tmdb_client, None)


def test_list_sessions_excludes_deleted_session(client: TestClient, tmp_path) -> None:
    source_path = tmp_path / "inbox"
    source_path.mkdir()
    target_path = tmp_path / "library"
    target_path.mkdir()

    create_response = client.post(
        "/scan-sessions",
        json={"source_path": str(source_path), "target_path": str(target_path)},
    )
    session_id = create_response.json()["id"]

    delete_response = client.delete(f"/scan-sessions/{session_id}")
    assert delete_response.status_code == 200

    list_response = client.get("/scan-sessions")
    assert list_response.status_code == 200
    assert all(session["id"] != session_id for session in list_response.json())
