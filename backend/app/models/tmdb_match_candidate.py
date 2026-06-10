from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .media_item import MediaItem


class TmdbMatchCandidate(Base):
    __tablename__ = "tmdb_match_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_item_id: Mapped[int] = mapped_column(ForeignKey("media_items.id"), index=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(512))
    overview: Mapped[str | None] = mapped_column(Text)
    release_date: Mapped[str | None] = mapped_column(String(32))
    first_air_date: Mapped[str | None] = mapped_column(String(32))
    year: Mapped[int | None] = mapped_column(Integer)
    poster_path: Mapped[str | None] = mapped_column(String(512))
    backdrop_path: Mapped[str | None] = mapped_column(String(512))
    vote_average: Mapped[float | None] = mapped_column(Float)
    popularity: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    media_item: Mapped["MediaItem"] = relationship(back_populates="tmdb_candidates")
