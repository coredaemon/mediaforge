from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import ScanSessionStatus

if TYPE_CHECKING:
    from .media_file import MediaFile
    from .media_item import MediaItem
    from .operation_plan import OperationPlan


class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    target_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ScanSessionStatus] = mapped_column(
        Enum(ScanSessionStatus),
        default=ScanSessionStatus.CREATED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String(2000))

    media_files: Mapped[list["MediaFile"]] = relationship(
        back_populates="scan_session",
        cascade="all, delete-orphan",
    )
    media_items: Mapped[list["MediaItem"]] = relationship(
        back_populates="scan_session",
        cascade="all, delete-orphan",
    )
    operation_plans: Mapped[list["OperationPlan"]] = relationship(
        back_populates="scan_session",
        cascade="all, delete-orphan",
    )
