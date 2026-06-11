from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import OperationStatus, OperationType, ValidationStatus

if TYPE_CHECKING:
    from .operation_plan import OperationPlan


class PlanOperation(Base):
    __tablename__ = "plan_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("operation_plans.id"), index=True)
    operation_type: Mapped[OperationType] = mapped_column(Enum(OperationType), nullable=False)
    status: Mapped[OperationStatus] = mapped_column(
        Enum(OperationStatus),
        default=OperationStatus.PENDING,
        nullable=False,
    )
    source_path: Mapped[str | None] = mapped_column(Text)
    target_path: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus),
        default=ValidationStatus.PENDING,
        nullable=False,
    )
    validation_error: Mapped[str | None] = mapped_column(String(2000))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped["OperationPlan"] = relationship(back_populates="operations")
