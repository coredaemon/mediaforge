from __future__ import annotations

import shutil
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.apply_operation_log import ApplyOperationLog
from ..models.enums import ApplyRunStatus, OperationStatus, OperationType, PlanStatus
from ..models.plan_operation import PlanOperation
from ..repositories.apply_run_repository import ApplyRunRepository
from ..repositories.operation_plan_repository import OperationPlanRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..schemas.operation_plan import PlanRollbackResult
from ..utils.path_safety import validate_source_in_session, validate_target_in_session
from ..utils.paths import normalize_path
from .apply_service import PlanApplyError
from .planning_service import OperationPlanNotFoundError


class RollbackService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.operation_plans = OperationPlanRepository(session)
        self.apply_runs = ApplyRunRepository(session)
        self.scan_sessions = ScanSessionRepository(session)

    async def rollback_plan(self, plan_id: int, confirm: bool) -> PlanRollbackResult:
        if not confirm:
            raise PlanApplyError("Rollback requires confirm=true")

        plan = await self.operation_plans.get_by_id(plan_id)
        if plan is None:
            raise OperationPlanNotFoundError(f"Operation plan {plan_id} was not found.")
        if plan.status not in {PlanStatus.APPLIED, PlanStatus.FAILED}:
            raise PlanApplyError(f"Plan status must be APPLIED or FAILED, got {plan.status}")

        apply_run = await self.apply_runs.get_latest_by_plan(plan_id)
        if apply_run is None:
            raise PlanApplyError("Plan has no apply runs")

        scan_session = await self.scan_sessions.get(plan.scan_session_id)
        if scan_session is None:
            raise PlanApplyError("Scan session not found")

        done_logs = list(await self.apply_runs.list_done_logs_for_run(apply_run.id))
        rolled_back_count = 0
        failed_count = 0
        error_message: str | None = None

        for log in done_logs:
            started_at = datetime.now(UTC)
            try:
                await self._rollback_log(log, scan_session.source_path, scan_session.target_path)
                finished_at = datetime.now(UTC)
                await self._create_rollback_log(log, OperationStatus.ROLLED_BACK, started_at, finished_at)
                rolled_back_count += 1
            except Exception as exc:  # noqa: BLE001 - rollback failure must be persisted for the user
                finished_at = datetime.now(UTC)
                error_message = str(exc)
                await self._create_rollback_log(
                    log,
                    OperationStatus.FAILED,
                    started_at,
                    finished_at,
                    error_message=error_message,
                )
                failed_count += 1
                break

        # done_operations/failed_operations record what the apply achieved and are
        # shown as such in the run history; the rollback's own counts travel in
        # PlanRollbackResult, so leave the apply's tally intact.
        apply_run.finished_at = datetime.now(UTC)
        apply_run.error_message = error_message

        if error_message:
            apply_run.status = ApplyRunStatus.FAILED
        else:
            apply_run.status = ApplyRunStatus.ROLLED_BACK
            plan.status = PlanStatus.ROLLED_BACK
            plan.rolled_back_at = datetime.now(UTC)
            await self._mark_operations_rolled_back(done_logs)

        await self.session.commit()
        await self.session.refresh(plan)
        await self.session.refresh(apply_run)

        return PlanRollbackResult(
            plan_id=plan.id,
            apply_run_id=apply_run.id,
            status=plan.status,
            total_operations=len(done_logs),
            rolled_back_operations=rolled_back_count,
            failed_operations=failed_count,
            error_message=error_message,
        )

    async def _rollback_log(self, log: ApplyOperationLog, source_root: str, target_root: str) -> None:
        rollback_data = log.rollback_data or {}
        if log.operation_type == OperationType.MOVE_FILE:
            source = rollback_data.get("to") or log.target_path
            target = rollback_data.get("from") or log.source_path
            if not source or not target:
                raise PlanApplyError("MOVE_FILE rollback data is incomplete")
            source_error = validate_target_in_session(source, target_root)
            if source_error:
                raise PlanApplyError(source_error)
            target_error = validate_source_in_session(target, source_root)
            if target_error:
                raise PlanApplyError(target_error)
            source_path = normalize_path(source)
            target_path = normalize_path(target)
            if not source_path.exists():
                raise PlanApplyError(f"Rollback source file missing: {source_path}")
            if target_path.exists():
                raise PlanApplyError(f"Rollback target path already exists: {target_path}")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_path), str(target_path))
            return

        if log.operation_type in {OperationType.WRITE_TEXT_FILE, OperationType.DOWNLOAD_FILE}:
            path = rollback_data.get("path") or log.target_path
            if not path:
                raise PlanApplyError(f"{log.operation_type} rollback data is incomplete")
            path_error = validate_target_in_session(path, target_root)
            if path_error:
                raise PlanApplyError(path_error)
            target_path = normalize_path(path)
            if target_path.exists():
                if not target_path.is_file():
                    raise PlanApplyError(f"Rollback target is not a file: {target_path}")
                target_path.unlink()
            return

        if log.operation_type == OperationType.CREATE_DIR:
            path = rollback_data.get("path") or rollback_data.get("target_path") or log.target_path
            if not path:
                raise PlanApplyError("CREATE_DIR rollback data is incomplete")
            path_error = validate_target_in_session(path, target_root)
            if path_error:
                raise PlanApplyError(path_error)
            target_path = normalize_path(path)
            if target_path.exists() and target_path.is_dir():
                try:
                    target_path.rmdir()
                except OSError:
                    return
            return

        raise PlanApplyError(f"Unsupported rollback operation type: {log.operation_type}")

    async def _mark_operations_rolled_back(self, logs: list[ApplyOperationLog]) -> None:
        for log in logs:
            operation = await self.session.get(PlanOperation, log.plan_operation_id)
            if operation is not None:
                operation.status = OperationStatus.ROLLED_BACK
                operation.error_message = None
                operation.finished_at = datetime.now(UTC)
        await self.session.flush()

    async def _create_rollback_log(
        self,
        original_log: ApplyOperationLog,
        status: OperationStatus,
        started_at: datetime,
        finished_at: datetime,
        error_message: str | None = None,
    ) -> None:
        rollback_data = self._rollback_log_data(original_log)
        self.session.add(
            ApplyOperationLog(
                apply_run_id=original_log.apply_run_id,
                plan_operation_id=original_log.plan_operation_id,
                operation_type=original_log.operation_type,
                status=status,
                source_path=original_log.target_path,
                target_path=original_log.source_path,
                error_message=error_message[:2000] if error_message else None,
                started_at=started_at,
                finished_at=finished_at,
                rollback_data=rollback_data,
            )
        )
        await self.session.flush()

    def _rollback_log_data(self, original_log: ApplyOperationLog) -> dict[str, str]:
        rollback_data = original_log.rollback_data or {}
        if original_log.operation_type == OperationType.MOVE_FILE:
            return {
                "from": str(rollback_data.get("to") or original_log.target_path or ""),
                "to": str(rollback_data.get("from") or original_log.source_path or ""),
            }
        path = rollback_data.get("path") or rollback_data.get("target_path") or original_log.target_path or ""
        return {"path": str(path)}
