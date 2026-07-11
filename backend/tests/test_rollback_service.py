from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.apply_operation_log import ApplyOperationLog
from backend.app.models.apply_run import ApplyRun
from backend.app.models.enums import ApplyRunStatus, OperationStatus, PlanStatus
from backend.app.repositories.operation_plan_repository import OperationPlanRepository
from backend.app.repositories.plan_operation_repository import PlanOperationRepository
from backend.app.services.apply_service import ApplyService, PlanApplyError
from backend.app.services.rollback_service import RollbackService
from backend.tests.test_apply_service import _create_ready_plan, _mock_http_client


async def _apply_plan(db_session: AsyncSession, tmp_path: Path) -> tuple[int, Path, Path]:
    plan_id, source, target, _ = await _create_ready_plan(db_session, tmp_path)
    await ApplyService(db_session, http_client=_mock_http_client()).apply_plan(plan_id, confirm=True)
    return plan_id, source, target


async def test_rollback_moves_file_deletes_nfo_and_removes_empty_dir(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    plan_id, source, target = await _apply_plan(db_session, tmp_path)
    movie_dir = target / "Movie (2024)"

    result = await RollbackService(db_session).rollback_plan(plan_id, confirm=True)

    assert result.status == PlanStatus.ROLLED_BACK
    assert (source / "Movie.2024.mkv").exists()
    assert not (movie_dir / "Movie (2024).mkv").exists()
    assert not (movie_dir / "movie.nfo").exists()
    assert not (movie_dir / "poster.jpg").exists()
    assert not movie_dir.exists()
    operations = await PlanOperationRepository(db_session).list_by_plan(plan_id)
    assert all(operation.status == OperationStatus.ROLLED_BACK for operation in operations)


async def test_rollback_after_partially_failed_apply_rolls_back_only_done_operations(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    plan_id, source, target, _ = await _create_ready_plan(db_session, tmp_path)
    response = MagicMock()
    response.status_code = 500
    response.headers = {}
    failing_client = MagicMock(spec=httpx.AsyncClient)
    failing_client.get = AsyncMock(return_value=response)
    failing_client.aclose = AsyncMock()
    await ApplyService(db_session, http_client=failing_client).apply_plan(plan_id, confirm=True)

    result = await RollbackService(db_session).rollback_plan(plan_id, confirm=True)

    movie_dir = target / "Movie (2024)"
    assert result.status == PlanStatus.ROLLED_BACK
    assert result.total_operations == 3
    assert (source / "Movie.2024.mkv").exists()
    assert not (movie_dir / "movie.nfo").exists()
    assert not (movie_dir / "poster.jpg").exists()


async def test_rollback_stops_when_original_source_path_is_occupied(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    plan_id, source, target = await _apply_plan(db_session, tmp_path)
    (source / "Movie.2024.mkv").write_bytes(b"occupied")

    result = await RollbackService(db_session).rollback_plan(plan_id, confirm=True)

    plan = await OperationPlanRepository(db_session).get_by_id(plan_id)
    run = (await db_session.execute(select(ApplyRun).where(ApplyRun.operation_plan_id == plan_id))).scalars().one()
    failed_logs = (
        await db_session.execute(
            select(ApplyOperationLog).where(
                ApplyOperationLog.apply_run_id == run.id,
                ApplyOperationLog.status == OperationStatus.FAILED,
            )
        )
    ).scalars().all()
    assert result.error_message is not None
    assert plan is not None
    assert plan.status == PlanStatus.APPLIED
    assert run.status == ApplyRunStatus.FAILED
    assert len(failed_logs) == 1
    assert (target / "Movie (2024)" / "Movie (2024).mkv").exists()


async def test_rollback_continues_when_created_nfo_is_already_deleted(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    plan_id, source, target = await _apply_plan(db_session, tmp_path)
    (target / "Movie (2024)" / "movie.nfo").unlink()

    result = await RollbackService(db_session).rollback_plan(plan_id, confirm=True)

    assert result.error_message is None
    assert (source / "Movie.2024.mkv").exists()
    assert not (target / "Movie (2024)").exists()


async def test_rollback_keeps_non_empty_directory_and_still_succeeds(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    plan_id, source, target = await _apply_plan(db_session, tmp_path)
    movie_dir = target / "Movie (2024)"
    extra = movie_dir / "keep.txt"
    extra.write_text("keep", encoding="utf-8")

    result = await RollbackService(db_session).rollback_plan(plan_id, confirm=True)

    assert result.status == PlanStatus.ROLLED_BACK
    assert (source / "Movie.2024.mkv").exists()
    assert movie_dir.exists()
    assert extra.exists()


async def test_rollback_preconditions(db_session: AsyncSession, tmp_path: Path) -> None:
    plan_id, _, _, _ = await _create_ready_plan(db_session, tmp_path)
    with pytest.raises(PlanApplyError):
        await RollbackService(db_session).rollback_plan(plan_id, confirm=False)
    with pytest.raises(PlanApplyError):
        await RollbackService(db_session).rollback_plan(plan_id, confirm=True)

    plan = await OperationPlanRepository(db_session).get_by_id(plan_id)
    assert plan is not None
    plan.status = PlanStatus.APPLIED
    await db_session.commit()

    with pytest.raises(PlanApplyError):
        await RollbackService(db_session).rollback_plan(plan_id, confirm=True)
