from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..models.enums import ApplyRunStatus, OperationStatus, OperationType, PlanStatus, ValidationStatus


class PlanOperationRead(BaseModel):
    id: int
    plan_id: int
    operation_type: OperationType
    status: OperationStatus
    source_path: str | None = None
    target_path: str | None = None
    payload_json: dict[str, Any] | None = None
    error_message: str | None = None
    validation_status: ValidationStatus
    validation_error: str | None = None
    validated_at: datetime | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OperationPlanRead(BaseModel):
    id: int
    scan_session_id: int
    status: PlanStatus
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None = None
    rolled_back_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PlanValidationResult(BaseModel):
    ok_count: int
    warning_count: int
    conflict_count: int
    operations: list[PlanOperationRead]


class PlanApplyRequest(BaseModel):
    confirm: bool


class PlanApplyResult(BaseModel):
    plan_id: int
    apply_run_id: int
    status: PlanStatus
    total_operations: int
    done_operations: int
    failed_operations: int
    error_message: str | None = None


class PlanRollbackResult(BaseModel):
    plan_id: int
    apply_run_id: int
    status: PlanStatus
    total_operations: int
    rolled_back_operations: int
    failed_operations: int
    error_message: str | None = None


class ApplyOperationLogRead(BaseModel):
    id: int
    apply_run_id: int
    plan_operation_id: int
    operation_type: OperationType
    status: OperationStatus
    source_path: str | None = None
    target_path: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    rollback_data: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class ApplyRunRead(BaseModel):
    id: int
    operation_plan_id: int
    started_at: datetime
    finished_at: datetime | None = None
    status: ApplyRunStatus
    total_operations: int
    done_operations: int
    failed_operations: int
    error_message: str | None = None
    logs: list[ApplyOperationLogRead] = []

    model_config = ConfigDict(from_attributes=True)
