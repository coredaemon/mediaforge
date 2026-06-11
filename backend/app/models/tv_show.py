from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import ReviewDecision

if TYPE_CHECKING:
    from .scan_session import ScanSession
    from .tv_episode import TvEpisode
    from .tv_grouping_run import TvGroupingRun
    from .tv_season import TvSeason


class TvShow(Base):
    __tablename__ = "tv_shows"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_session_id: Mapped[int] = mapped_column(ForeignKey("scan_sessions.id"), index=True)
    local_group_id: Mapped[str | None] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(512))
    year: Mapped[int | None] = mapped_column(Integer)
    first_air_date: Mapped[str | None] = mapped_column(String(32))
    tmdb_id: Mapped[int | None] = mapped_column(Integer, index=True)
    imdb_id: Mapped[str | None] = mapped_column(String(32))
    tvdb_id: Mapped[int | None] = mapped_column(Integer)
    wikidata_id: Mapped[str | None] = mapped_column(String(64))
    overview: Mapped[str | None] = mapped_column(Text)
    poster_path: Mapped[str | None] = mapped_column(String(512))
    poster_url: Mapped[str | None] = mapped_column(String(1024))
    backdrop_path: Mapped[str | None] = mapped_column(String(512))
    backdrop_url: Mapped[str | None] = mapped_column(String(1024))
    language: Mapped[str | None] = mapped_column(String(16))
    match_source: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float)
    review_decision: Mapped[str] = mapped_column(String(32), default=ReviewDecision.PENDING, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_reasoning_summary: Mapped[str | None] = mapped_column(Text)
    local_ai_json: Mapped[dict | None] = mapped_column(JSON)
    gemini_audit_json: Mapped[dict | None] = mapped_column(JSON)
    warnings: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    scan_session: Mapped["ScanSession"] = relationship()
    seasons: Mapped[list["TvSeason"]] = relationship(back_populates="show", cascade="all, delete-orphan")
    episodes: Mapped[list["TvEpisode"]] = relationship(back_populates="show", cascade="all, delete-orphan")
    grouping_runs: Mapped[list["TvGroupingRun"]] = relationship(back_populates="show")
