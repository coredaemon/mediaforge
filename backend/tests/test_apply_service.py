from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.apply_operation_log import ApplyOperationLog
from backend.app.models.apply_run import ApplyRun
from backend.app.models.enums import (
    ApplyRunStatus,
    MediaFileKind,
    MediaItemStatus,
    MediaType,
    OperationStatus,
    OperationType,
    PlanStatus,
    ReviewDecision,
)
from backend.app.models.media_file import MediaFile
from backend.app.models.media_item import MediaItem
from backend.app.models.operation_plan import OperationPlan
from backend.app.models.plan_operation import PlanOperation
from backend.app.repositories.media_file_repository import MediaFileRepository
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.repositories.operation_plan_repository import OperationPlanRepository
from backend.app.repositories.plan_operation_repository import PlanOperationRepository
from backend.app.services.apply_service import ApplyService, PlanApplyError
from backend.app.services.planning_service import NoMatchedItemsError, PlanningService
from backend.app.services.scan_session_service import ScanSessionService


async def _create_ready_plan(db_session: AsyncSession, tmp_path: Path) -> tuple[int, Path, Path, MediaItem]:
    source = tmp_path / "inbox"
    target = tmp_path / "library"
    source.mkdir()
    target.mkdir()
    video = source / "Movie.2024.mkv"
    video.write_bytes(b"video-bytes")

    session = await ScanSessionService(db_session).create_scan_session(str(source), str(target))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.MATCHED,
            parsed_title="Movie",
            matched_title="Movie",
            matched_year=2024,
            tmdb_id=99,
            localized_title="Фильм",
            localized_overview="Описание",
            imdb_id="tt9999999",
            review_decision=ReviewDecision.APPROVED,
            needs_review=False,
        )
    )
    await MediaFileRepository(db_session).add(
        MediaFile(
            scan_session_id=session.id,
            media_item_id=item.id,
            path=str(video.resolve()),
            file_name=video.name,
            extension=".mkv",
            size_bytes=video.stat().st_size,
            modified_at=datetime.fromtimestamp(video.stat().st_mtime, tz=UTC),
            kind=MediaFileKind.VIDEO,
            is_video=True,
            is_subtitle=False,
            is_sidecar=False,
        )
    )
    movie_dir = target / "Movie (2024)"
    plan = await OperationPlanRepository(db_session).create(
        OperationPlan(scan_session_id=session.id, status=PlanStatus.READY)
    )
    ops = PlanOperationRepository(db_session)
    await ops.create(
        PlanOperation(
            plan_id=plan.id,
            operation_type=OperationType.CREATE_DIR,
            status=OperationStatus.PENDING,
            target_path=str(movie_dir),
            payload_json={"media_item_id": item.id},
        )
    )
    await ops.create(
        PlanOperation(
            plan_id=plan.id,
            operation_type=OperationType.MOVE_FILE,
            status=OperationStatus.PENDING,
            source_path=str(video.resolve()),
            target_path=str(movie_dir / "Movie (2024).mkv"),
            payload_json={"media_item_id": item.id},
        )
    )
    await ops.create(
        PlanOperation(
            plan_id=plan.id,
            operation_type=OperationType.WRITE_TEXT_FILE,
            status=OperationStatus.PENDING,
            target_path=str(movie_dir / "movie.nfo"),
            payload_json={"media_item_id": item.id, "nfo_type": "movie"},
        )
    )
    await ops.create(
        PlanOperation(
            plan_id=plan.id,
            operation_type=OperationType.DOWNLOAD_FILE,
            status=OperationStatus.PENDING,
            source_path="https://image.tmdb.org/t/p/original/poster.jpg",
            target_path=str(movie_dir / "poster.jpg"),
            payload_json={"media_item_id": item.id, "asset_type": "poster"},
        )
    )
    await db_session.commit()
    return plan.id, source, target, item


def _mock_http_client(content: bytes = b"image-bytes") -> httpx.AsyncClient:
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-type": "image/jpeg"}
    response.content = content
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    client.aclose = AsyncMock()
    return client


async def test_apply_requires_confirm_true(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)
    with pytest.raises(PlanApplyError):
        await ApplyService(db_session).apply_plan(plan_id, confirm=False)


async def test_start_apply_returns_running_run(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)

    result = await ApplyService(db_session).start_apply(plan_id, confirm=True)

    plan = await OperationPlanRepository(db_session).get_by_id(plan_id)
    run = await db_session.get(ApplyRun, result.apply_run_id)
    assert plan is not None
    assert run is not None
    assert result.status == PlanStatus.APPLYING
    assert plan.status == PlanStatus.APPLYING
    assert run.status == ApplyRunStatus.RUNNING
    assert result.done_operations == 0


async def test_execute_apply_run_finishes_started_apply(db_session: AsyncSession, tmp_path) -> None:
    plan_id, source, target, _ = await _create_ready_plan(db_session, tmp_path)
    service = ApplyService(db_session, http_client=_mock_http_client())
    started = await service.start_apply(plan_id, confirm=True)

    result = await service.execute_apply_run(started.apply_run_id)

    assert result.status == PlanStatus.APPLIED
    assert not (source / "Movie.2024.mkv").exists()
    assert (target / "Movie (2024)" / "Movie (2024).mkv").exists()


async def test_start_apply_rejects_plan_already_applying(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)
    await ApplyService(db_session).start_apply(plan_id, confirm=True)

    with pytest.raises(PlanApplyError) as exc_info:
        await ApplyService(db_session).start_apply(plan_id, confirm=True)

    assert exc_info.value.error_code == "apply_in_progress"


async def test_apply_creates_directories(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, target, _ = await _create_ready_plan(db_session, tmp_path)
    client = _mock_http_client()
    await ApplyService(db_session, http_client=client).apply_plan(plan_id, confirm=True)
    assert (target / "Movie (2024)").is_dir()


async def test_apply_moves_file(db_session: AsyncSession, tmp_path) -> None:
    plan_id, source, target, _ = await _create_ready_plan(db_session, tmp_path)
    client = _mock_http_client()
    await ApplyService(db_session, http_client=client).apply_plan(plan_id, confirm=True)
    assert not (source / "Movie.2024.mkv").exists()
    assert (target / "Movie (2024)" / "Movie (2024).mkv").exists()


async def test_apply_writes_text_file(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, target, _ = await _create_ready_plan(db_session, tmp_path)
    client = _mock_http_client()
    await ApplyService(db_session, http_client=client).apply_plan(plan_id, confirm=True)
    nfo = target / "Movie (2024)" / "movie.nfo"
    assert nfo.exists()
    assert "<movie>" in nfo.read_text(encoding="utf-8")
    assert "Фильм" in nfo.read_text(encoding="utf-8")


async def test_apply_downloads_image_from_mocked_httpx(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, target, _ = await _create_ready_plan(db_session, tmp_path)
    client = _mock_http_client(b"poster-data")
    await ApplyService(db_session, http_client=client).apply_plan(plan_id, confirm=True)
    poster = target / "Movie (2024)" / "poster.jpg"
    assert poster.exists()
    assert poster.read_bytes() == b"poster-data"


async def test_apply_rejects_non_tmdb_download_url(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan_id)
    download = next(op for op in operations if op.operation_type == OperationType.DOWNLOAD_FILE)
    download.source_path = "https://evil.example/poster.jpg"
    await db_session.commit()

    with pytest.raises(PlanApplyError):
        await ApplyService(db_session, http_client=_mock_http_client()).apply_plan(plan_id, confirm=True)


async def test_apply_stops_on_conflict(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, target, _ = await _create_ready_plan(db_session, tmp_path)
    existing = target / "Movie (2024)" / "Movie (2024).mkv"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already")
    with pytest.raises(PlanApplyError):
        await ApplyService(db_session, http_client=_mock_http_client()).apply_plan(plan_id, confirm=True)


async def test_apply_updates_operation_statuses(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)
    await ApplyService(db_session, http_client=_mock_http_client()).apply_plan(plan_id, confirm=True)
    operations = await PlanOperationRepository(db_session).list_by_plan(plan_id)
    done_ops = [op for op in operations if op.status == OperationStatus.DONE]
    assert len(done_ops) >= 3


async def test_apply_creates_apply_run_and_log_entries(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)
    await ApplyService(db_session, http_client=_mock_http_client()).apply_plan(plan_id, confirm=True)
    runs = (await db_session.execute(select(ApplyRun).where(ApplyRun.operation_plan_id == plan_id))).scalars().all()
    assert len(runs) == 1
    logs = (await db_session.execute(select(ApplyOperationLog).where(ApplyOperationLog.apply_run_id == runs[0].id))).scalars().all()
    assert len(logs) >= 3


async def test_apply_plan_status_applied_on_success(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)
    result = await ApplyService(db_session, http_client=_mock_http_client()).apply_plan(plan_id, confirm=True)
    plan = await OperationPlanRepository(db_session).get_by_id(plan_id)
    assert plan is not None
    assert plan.status == PlanStatus.APPLIED
    assert plan.applied_at is not None
    assert result.status == PlanStatus.APPLIED


async def test_apply_plan_status_failed_on_error(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)
    response = MagicMock()
    response.status_code = 500
    response.headers = {}
    failing_client = MagicMock(spec=httpx.AsyncClient)
    failing_client.get = AsyncMock(return_value=response)
    failing_client.aclose = AsyncMock()

    result = await ApplyService(db_session, http_client=failing_client).apply_plan(plan_id, confirm=True)
    assert result.failed_operations == 1
    plan = await OperationPlanRepository(db_session).get_by_id(plan_id)
    assert plan is not None
    assert plan.status == PlanStatus.FAILED
    runs = (await db_session.execute(select(ApplyRun).where(ApplyRun.operation_plan_id == plan_id))).scalars().all()
    assert runs[0].status == ApplyRunStatus.FAILED


async def test_apply_does_not_overwrite_existing_target(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, target, _ = await _create_ready_plan(db_session, tmp_path)
    existing = target / "Movie (2024)" / "poster.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"keep")
    with pytest.raises(PlanApplyError):
        await ApplyService(db_session, http_client=_mock_http_client()).apply_plan(plan_id, confirm=True)
    assert existing.read_bytes() == b"keep"


async def test_ignored_deferred_items_not_in_plan(db_session: AsyncSession, tmp_path) -> None:
    source = tmp_path / "inbox"
    target = tmp_path / "library"
    source.mkdir()
    target.mkdir()
    video = source / "Ignored.mkv"
    video.write_bytes(b"x")
    session = await ScanSessionService(db_session).create_scan_session(str(source), str(target))
    await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.MATCHED,
            matched_title="Ignored",
            matched_year=2020,
            tmdb_id=1,
            review_decision=ReviewDecision.IGNORED,
        )
    )
    await MediaFileRepository(db_session).add(
        MediaFile(
            scan_session_id=session.id,
            path=str(video.resolve()),
            file_name=video.name,
            extension=".mkv",
            kind=MediaFileKind.VIDEO,
            is_video=True,
            is_subtitle=False,
            is_sidecar=False,
        )
    )
    await db_session.commit()
    with pytest.raises(NoMatchedItemsError):
        await PlanningService(db_session).create_plan_for_scan_session(session.id)
