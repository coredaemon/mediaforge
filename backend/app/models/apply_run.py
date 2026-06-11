from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import ApplyRunStatus

if TYPE_CHECKING:
    from .apply_operation_log import ApplyOperationLog
    from .operation_plan import OperationPlan


class ApplyRun(Base):
    __tablename__ = "apply_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_plan_id: Mapped[int] = mapped_column(ForeignKey("operation_plans.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ApplyRunStatus] = mapped_column(
        Enum(ApplyRunStatus),
        default=ApplyRunStatus.RUNNING,
        nullable=False,
    )
    total_operations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    done_operations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_operations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    plan: Mapped["OperationPlan"] = relationship(back_populates="apply_runs")
    logs: Mapped[list["ApplyOperationLog"]] = relationship(
        back_populates="apply_run",
        cascade="all, delete-orphan",
    )
