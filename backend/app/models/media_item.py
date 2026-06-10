from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import MediaItemStatus, MediaType

if TYPE_CHECKING:
    from .media_file import MediaFile
    from .scan_session import ScanSession
    from .tmdb_match_candidate import TmdbMatchCandidate


class MediaItem(Base):
    __tablename__ = "media_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_session_id: Mapped[int] = mapped_column(ForeignKey("scan_sessions.id"), index=True)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType), default=MediaType.UNKNOWN, nullable=False)
    status: Mapped[MediaItemStatus] = mapped_column(
        Enum(MediaItemStatus),
        default=MediaItemStatus.DISCOVERED,
        nullable=False,
    )
    original_title: Mapped[str | None] = mapped_column(String(512))
    parsed_title: Mapped[str | None] = mapped_column(String(512))
    year: Mapped[int | None] = mapped_column(Integer)
    season_number: Mapped[int | None] = mapped_column(Integer)
    episode_number: Mapped[int | None] = mapped_column(Integer)
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    tmdb_media_type: Mapped[str | None] = mapped_column(String(32))
    matched_title: Mapped[str | None] = mapped_column(String(512))
    matched_year: Mapped[int | None] = mapped_column(Integer)
    match_confidence: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    scan_session: Mapped["ScanSession"] = relationship(back_populates="media_items")
    media_files: Mapped[list["MediaFile"]] = relationship(back_populates="media_item")
    tmdb_candidates: Mapped[list["TmdbMatchCandidate"]] = relationship(
        back_populates="media_item",
        cascade="all, delete-orphan",
    )
