from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import PlanStatus
from ..models.operation_plan import OperationPlan


class OperationPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, plan: OperationPlan) -> OperationPlan:
        self.session.add(plan)
        await self.session.flush()
        return plan

    async def claim_for_apply(self, plan_id: int) -> bool:
        """Move a plan READY -> APPLYING, returning False if it was already claimed.

        A read-then-write would let two concurrent apply requests both see READY and
        both start moving the same files, so the transition has to be one statement.
        """
        result = await self.session.execute(
            update(OperationPlan)
            .where(OperationPlan.id == plan_id, OperationPlan.status == PlanStatus.READY)
            .values(status=PlanStatus.APPLYING)
            .execution_options(synchronize_session="fetch")
        )
        return result.rowcount == 1

    async def get_by_id(self, plan_id: int) -> OperationPlan | None:
        return await self.session.get(OperationPlan, plan_id)

    async def get_latest_by_scan_session(self, scan_session_id: int) -> OperationPlan | None:
        result = await self.session.execute(
            select(OperationPlan)
            .where(OperationPlan.scan_session_id == scan_session_id)
            .order_by(OperationPlan.created_at.desc(), OperationPlan.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_scan_session(self, scan_session_id: int) -> Sequence[OperationPlan]:
        result = await self.session.execute(
            select(OperationPlan)
            .where(OperationPlan.scan_session_id == scan_session_id)
            .order_by(OperationPlan.created_at.desc(), OperationPlan.id.desc())
        )
        return result.scalars().all()

    async def delete(self, plan: OperationPlan) -> None:
        await self.session.delete(plan)
        await self.session.flush()

    async def delete_draft_or_ready_for_scan_session(self, scan_session_id: int) -> None:
        result = await self.session.execute(
            select(OperationPlan).where(
                OperationPlan.scan_session_id == scan_session_id,
                OperationPlan.status.in_([PlanStatus.DRAFT, PlanStatus.READY]),
            )
        )
        for plan in result.scalars().all():
            await self.delete(plan)
