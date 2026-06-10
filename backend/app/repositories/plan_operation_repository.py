from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.plan_operation import PlanOperation


class PlanOperationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, operation: PlanOperation) -> PlanOperation:
        self.session.add(operation)
        await self.session.flush()
        return operation

    async def list_by_plan(self, plan_id: int) -> Sequence[PlanOperation]:
        result = await self.session.execute(
            select(PlanOperation)
            .where(PlanOperation.plan_id == plan_id)
            .order_by(PlanOperation.id.asc())
        )
        return result.scalars().all()

    async def delete_for_plan(self, plan_id: int) -> None:
        await self.session.execute(delete(PlanOperation).where(PlanOperation.plan_id == plan_id))
