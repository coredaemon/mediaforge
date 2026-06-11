from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import OperationStatus, OperationType

if TYPE_CHECKING:
    from .apply_run import ApplyRun


class ApplyOperationLog(Base):
    __tablename__ = "apply_operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    apply_run_id: Mapped[int] = mapped_column(ForeignKey("apply_runs.id"), index=True)
    plan_operation_id: Mapped[int] = mapped_column(
        ForeignKey("plan_operations.id", ondelete="CASCADE"),
        index=True,
    )
    operation_type: Mapped[OperationType] = mapped_column(Enum(OperationType), nullable=False)
    status: Mapped[OperationStatus] = mapped_column(Enum(OperationStatus), nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text)
    target_path: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rollback_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    apply_run: Mapped["ApplyRun"] = relationship(back_populates="logs")
