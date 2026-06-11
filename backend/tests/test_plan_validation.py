from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaFileKind, MediaItemStatus, MediaType, OperationStatus, OperationType, PlanStatus, ValidationStatus
from backend.app.models.media_file import MediaFile
from backend.app.models.media_item import MediaItem
from backend.app.models.operation_plan import OperationPlan
from backend.app.models.plan_operation import PlanOperation
from backend.app.repositories.media_file_repository import MediaFileRepository
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.repositories.operation_plan_repository import OperationPlanRepository
from backend.app.repositories.plan_operation_repository import PlanOperationRepository
from backend.app.services.plan_validation_service import PlanValidationService
from backend.app.services.scan_session_service import ScanSessionService


async def _setup_plan(db_session: AsyncSession, tmp_path: Path) -> tuple[int, int, Path, Path]:
    source = tmp_path / "inbox"
    target = tmp_path / "library"
    source.mkdir()
    target.mkdir()
    video = source / "movie.mkv"
    video.write_bytes(b"video-content")

    session = await ScanSessionService(db_session).create_scan_session(str(source), str(target))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=session.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.MATCHED,
            matched_title="Movie",
            matched_year=2024,
            tmdb_id=1,
        )
    )
    media_file = await MediaFileRepository(db_session).add(
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
    plan = await OperationPlanRepository(db_session).create(
        OperationPlan(scan_session_id=session.id, status=PlanStatus.READY)
    )
    await db_session.commit()
    return plan.id, media_file.id, source, target


async def _add_operation(
    db_session: AsyncSession,
    plan_id: int,
    operation_type: OperationType,
    source_path: str | None = None,
    target_path: str | None = None,
) -> PlanOperation:
    op = await PlanOperationRepository(db_session).create(
        PlanOperation(
            plan_id=plan_id,
            operation_type=operation_type,
            status=OperationStatus.PENDING,
            source_path=source_path,
            target_path=target_path,
            payload_json={"media_item_id": 1},
        )
    )
    await db_session.commit()
    return op


async def test_validate_ok_for_normal_operations(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, source, target = await _setup_plan(db_session, tmp_path)
    movie_dir = target / "Movie (2024)"
    await _add_operation(db_session, plan_id, OperationType.CREATE_DIR, target_path=str(movie_dir))
    await _add_operation(
        db_session,
        plan_id,
        OperationType.MOVE_FILE,
        source_path=str((source / "movie.mkv").resolve()),
        target_path=str(movie_dir / "Movie (2024).mkv"),
    )

    result = await PlanValidationService(db_session).validate_plan(plan_id)
    assert result.ok_count >= 2
    assert result.conflict_count == 0


async def test_validate_conflict_if_target_file_exists(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, source, target = await _setup_plan(db_session, tmp_path)
    existing = target / "Movie (2024)" / "Movie (2024).mkv"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"exists")
    await _add_operation(
        db_session,
        plan_id,
        OperationType.MOVE_FILE,
        source_path=str((source / "movie.mkv").resolve()),
        target_path=str(existing),
    )

    result = await PlanValidationService(db_session).validate_plan(plan_id)
    assert result.conflict_count == 1
    assert result.operations[0].validation_status == ValidationStatus.CONFLICT


async def test_validate_conflict_if_source_missing(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, target = await _setup_plan(db_session, tmp_path)
    await _add_operation(
        db_session,
        plan_id,
        OperationType.MOVE_FILE,
        source_path=str(tmp_path / "missing.mkv"),
        target_path=str(target / "Movie (2024)" / "Movie (2024).mkv"),
    )

    result = await PlanValidationService(db_session).validate_plan(plan_id)
    assert result.conflict_count == 1


async def test_validate_conflict_if_source_changed_since_scan(db_session: AsyncSession, tmp_path) -> None:
    plan_id, media_file_id, source, target = await _setup_plan(db_session, tmp_path)
    video = source / "movie.mkv"
    video.write_bytes(b"changed-content")
    media_file = await db_session.get(MediaFile, media_file_id)
    assert media_file is not None
    media_file.size_bytes = 1
    await db_session.commit()

    await _add_operation(
        db_session,
        plan_id,
        OperationType.MOVE_FILE,
        source_path=str(video.resolve()),
        target_path=str(target / "Movie (2024)" / "Movie (2024).mkv"),
    )

    result = await PlanValidationService(db_session).validate_plan(plan_id)
    assert result.conflict_count == 1


async def test_validate_conflict_if_target_escapes_root(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, source, _ = await _setup_plan(db_session, tmp_path)
    await _add_operation(
        db_session,
        plan_id,
        OperationType.MOVE_FILE,
        source_path=str((source / "movie.mkv").resolve()),
        target_path=str(tmp_path / "outside" / "movie.mkv"),
    )

    result = await PlanValidationService(db_session).validate_plan(plan_id)
    assert result.conflict_count == 1


async def test_validate_conflict_if_target_dir_exists_as_file(db_session: AsyncSession, tmp_path) -> None:
    plan_id, _, _, target = await _setup_plan(db_session, tmp_path)
    blocker = target / "Movie (2024)"
    blocker.write_bytes(b"file-not-dir")
    await _add_operation(db_session, plan_id, OperationType.CREATE_DIR, target_path=str(blocker))

    result = await PlanValidationService(db_session).validate_plan(plan_id)
    assert result.conflict_count == 1
