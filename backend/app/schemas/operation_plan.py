from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..models.enums import OperationStatus, OperationType, PlanStatus


class PlanOperationRead(BaseModel):
    id: int
    plan_id: int
    operation_type: OperationType
    status: OperationStatus
    source_path: str | None = None
    target_path: str | None = None
    payload_json: dict[str, Any] | None = None
    error_message: str | None = None
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
