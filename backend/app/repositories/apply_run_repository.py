from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.apply_operation_log import ApplyOperationLog
from ..models.apply_run import ApplyRun
from ..models.enums import OperationStatus
from ..models.operation_plan import OperationPlan


class ApplyRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, apply_run: ApplyRun) -> ApplyRun:
        self.session.add(apply_run)
        await self.session.flush()
        return apply_run

    async def list_by_plan(self, plan_id: int) -> Sequence[ApplyRun]:
        result = await self.session.execute(
            select(ApplyRun)
            .options(selectinload(ApplyRun.logs))
            .where(ApplyRun.operation_plan_id == plan_id)
            .order_by(ApplyRun.started_at.desc(), ApplyRun.id.desc())
        )
        return result.scalars().all()

    async def get_latest_by_plan(self, plan_id: int) -> ApplyRun | None:
        result = await self.session.execute(
            select(ApplyRun)
            .where(ApplyRun.operation_plan_id == plan_id)
            .order_by(ApplyRun.started_at.desc(), ApplyRun.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_done_logs_for_run(self, apply_run_id: int) -> Sequence[ApplyOperationLog]:
        result = await self.session.execute(
            select(ApplyOperationLog)
            .where(
                ApplyOperationLog.apply_run_id == apply_run_id,
                ApplyOperationLog.status == OperationStatus.DONE,
            )
            .order_by(ApplyOperationLog.id.desc())
        )
        return result.scalars().all()

    async def delete_logs_for_scan_session(self, scan_session_id: int) -> None:
        plan_ids_subq = select(OperationPlan.id).where(OperationPlan.scan_session_id == scan_session_id)
        run_ids_subq = select(ApplyRun.id).where(ApplyRun.operation_plan_id.in_(plan_ids_subq))
        await self.session.execute(delete(ApplyOperationLog).where(ApplyOperationLog.apply_run_id.in_(run_ids_subq)))

    async def delete_runs_for_scan_session(self, scan_session_id: int) -> None:
        plan_ids_subq = select(OperationPlan.id).where(OperationPlan.scan_session_id == scan_session_id)
        await self.session.execute(delete(ApplyRun).where(ApplyRun.operation_plan_id.in_(plan_ids_subq)))
