from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db.session import get_session
from ...models.operation_plan import OperationPlan
from ...models.plan_operation import PlanOperation
from ...schemas.operation_plan import (
    ApplyRunRead,
    OperationPlanRead,
    PlanApplyRequest,
    PlanApplyResult,
    PlanOperationRead,
    PlanRollbackResult,
    PlanValidationResult,
)
from ...services.apply_service import ApplyService, PlanApplyError, schedule_apply_run
from ...services.plan_validation_service import PlanValidationService
from ...services.planning_service import OperationPlanNotFoundError, PlanningService
from ...services.rollback_service import RollbackService

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


@router.post("/{plan_id}/validate", response_model=PlanValidationResult)
async def validate_operation_plan(
    plan_id: int,
    session: AsyncSession = Depends(get_session),
) -> PlanValidationResult:
    try:
        return await PlanValidationService(session).validate_plan(plan_id)
    except OperationPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{plan_id}/apply", response_model=PlanApplyResult)
async def apply_operation_plan(
    plan_id: int,
    payload: PlanApplyRequest,
    session: AsyncSession = Depends(get_session),
) -> PlanApplyResult:
    try:
        result = await ApplyService(session).start_apply(plan_id, confirm=payload.confirm)
        bind = session.bind
        if bind is None:
            schedule_apply_run(result.apply_run_id)
        else:
            schedule_apply_run(result.apply_run_id, async_sessionmaker(bind, expire_on_commit=False))
        return result
    except OperationPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanApplyError as exc:
        if exc.error_code == "apply_in_progress":
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if exc.error_code:
            raise HTTPException(status_code=400, detail={"error_code": exc.error_code, "message": str(exc)}) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{plan_id}/rollback", response_model=PlanRollbackResult)
async def rollback_operation_plan(
    plan_id: int,
    payload: PlanApplyRequest,
    session: AsyncSession = Depends(get_session),
) -> PlanRollbackResult:
    try:
        return await RollbackService(session).rollback_plan(plan_id, confirm=payload.confirm)
    except OperationPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanApplyError as exc:
        if exc.error_code:
            raise HTTPException(status_code=400, detail={"error_code": exc.error_code, "message": str(exc)}) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{plan_id}/apply-runs", response_model=list[ApplyRunRead])
async def list_operation_plan_apply_runs(
    plan_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[ApplyRunRead]:
    try:
        return await ApplyService(session).list_apply_runs(plan_id)
    except OperationPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
