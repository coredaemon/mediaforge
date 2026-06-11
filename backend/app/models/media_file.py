from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import MediaFileKind

if TYPE_CHECKING:
    from .media_item import MediaItem
    from .scan_session import ScanSession


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_session_id: Mapped[int] = mapped_column(ForeignKey("scan_sessions.id"), index=True)
    media_item_id: Mapped[int | None] = mapped_column(ForeignKey("media_items.id"), index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reused_from_memory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    kind: Mapped[MediaFileKind] = mapped_column(Enum(MediaFileKind), nullable=False)
    is_video: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_subtitle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_sidecar: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scan_error: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scan_session: Mapped["ScanSession"] = relationship(back_populates="media_files")
    media_item: Mapped["MediaItem | None"] = relationship(back_populates="media_files")
