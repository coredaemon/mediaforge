from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .media_file import MediaFile
    from .tv_season import TvSeason
    from .tv_show import TvShow


class TvEpisode(Base):
    __tablename__ = "tv_episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("tv_shows.id"), index=True)
    season_id: Mapped[int | None] = mapped_column(ForeignKey("tv_seasons.id"), index=True)
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id"), index=True)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Set only for a merged release holding two aired episodes (S02E01E02).
    episode_number_end: Mapped[int | None] = mapped_column(Integer)
    absolute_number: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(512))
    overview: Mapped[str | None] = mapped_column(Text)
    air_date: Mapped[str | None] = mapped_column(String(32))
    tmdb_episode_id: Mapped[int | None] = mapped_column(Integer)
    source_path: Mapped[str | None] = mapped_column(Text)
    target_path: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    issue: Mapped[str | None] = mapped_column(Text)
    warning: Mapped[str | None] = mapped_column(Text)
    match_source: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    show: Mapped["TvShow"] = relationship(back_populates="episodes")
    season: Mapped["TvSeason | None"] = relationship(back_populates="episodes")
    source_file: Mapped["MediaFile | None"] = relationship()
