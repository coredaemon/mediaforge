from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import PlanStatus

if TYPE_CHECKING:
    from .apply_run import ApplyRun
    from .plan_operation import PlanOperation
    from .scan_session import ScanSession


class OperationPlan(Base):
    __tablename__ = "operation_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_session_id: Mapped[int] = mapped_column(ForeignKey("scan_sessions.id"), index=True)
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus), default=PlanStatus.DRAFT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scan_session: Mapped["ScanSession"] = relationship(back_populates="operation_plans")
    operations: Mapped[list["PlanOperation"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
    )
    apply_runs: Mapped[list["ApplyRun"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
    )
