from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...models.operation_plan import OperationPlan
from ...models.plan_operation import PlanOperation
from ...schemas.operation_plan import OperationPlanRead, PlanOperationRead
from ...services.planning_service import OperationPlanNotFoundError, PlanningService

router = APIRouter(prefix="/operation-plans", tags=["operation-plans"])


@router.get("/{plan_id}", response_model=OperationPlanRead)
async def get_operation_plan(plan_id: int, session: AsyncSession = Depends(get_session)) -> OperationPlan:
    try:
        return await PlanningService(session).get_operation_plan(plan_id)
    except OperationPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{plan_id}/operations", response_model=list[PlanOperationRead])
async def list_operation_plan_operations(
    plan_id: int,
    session: AsyncSession = Depends(get_session),
) -> Sequence[PlanOperation]:
    try:
        return await PlanningService(session).list_plan_operations(plan_id)
    except OperationPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
