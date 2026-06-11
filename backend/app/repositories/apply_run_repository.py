from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.apply_run import ApplyRun


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
            .where(ApplyRun.operation_plan_id == plan_id)
            .order_by(ApplyRun.started_at.desc(), ApplyRun.id.desc())
        )
        return result.scalars().all()
