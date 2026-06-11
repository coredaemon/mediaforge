from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .enums import MediaItemStatus, MediaType, ReviewDecision

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
    imdb_id: Mapped[str | None] = mapped_column(String(32))
    tvdb_id: Mapped[int | None] = mapped_column(Integer)
    wikidata_id: Mapped[str | None] = mapped_column(String(64))
    localized_title: Mapped[str | None] = mapped_column(String(512))
    localized_overview: Mapped[str | None] = mapped_column(Text)
    tmdb_original_title: Mapped[str | None] = mapped_column(String(512))
    poster_path: Mapped[str | None] = mapped_column(String(512))
    backdrop_path: Mapped[str | None] = mapped_column(String(512))
    poster_url: Mapped[str | None] = mapped_column(String(1024))
    backdrop_url: Mapped[str | None] = mapped_column(String(1024))
    metadata_language: Mapped[str | None] = mapped_column(String(16))
    reused_from_memory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    memory_status: Mapped[str | None] = mapped_column(String(32))
    ai_clean_title: Mapped[str | None] = mapped_column(String(512))
    ai_year: Mapped[int | None] = mapped_column(Integer)
    ai_media_type: Mapped[str | None] = mapped_column(String(32))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_junk_tokens: Mapped[list[str] | None] = mapped_column(JSON)
    ai_explanation: Mapped[str | None] = mapped_column(Text)
    gemini_clean_title: Mapped[str | None] = mapped_column(String(512))
    gemini_year: Mapped[int | None] = mapped_column(Integer)
    gemini_media_type: Mapped[str | None] = mapped_column(String(32))
    gemini_confidence: Mapped[float | None] = mapped_column(Float)
    gemini_junk_tokens: Mapped[list[str] | None] = mapped_column(JSON)
    gemini_explanation: Mapped[str | None] = mapped_column(Text)
    tmdb_queries: Mapped[list[str] | None] = mapped_column(JSON)
    local_ai_status: Mapped[str | None] = mapped_column(String(32), default="not_run")
    local_ai_duration_ms: Mapped[int | None] = mapped_column(Integer)
    local_ai_error: Mapped[str | None] = mapped_column(Text)
    local_ai_response_valid_json: Mapped[bool | None] = mapped_column(Boolean)
    local_ai_model: Mapped[str | None] = mapped_column(String(256))
    gemini_status: Mapped[str | None] = mapped_column(String(32), default="not_run")
    gemini_duration_ms: Mapped[int | None] = mapped_column(Integer)
    gemini_error: Mapped[str | None] = mapped_column(Text)
    gemini_response_valid_json: Mapped[bool | None] = mapped_column(Boolean)
    gemini_model: Mapped[str | None] = mapped_column(String(256))
    confidence: Mapped[float | None] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_decision: Mapped[str] = mapped_column(String(32), default=ReviewDecision.PENDING, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    manual_title: Mapped[str | None] = mapped_column(String(512))
    manual_year: Mapped[int | None] = mapped_column(Integer)
    manual_tmdb_id: Mapped[int | None] = mapped_column(Integer)
    manual_imdb_id: Mapped[str | None] = mapped_column(String(32))
    manual_tvdb_id: Mapped[int | None] = mapped_column(Integer)
    manual_media_type: Mapped[str | None] = mapped_column(String(32))
    sidecar_title: Mapped[str | None] = mapped_column(String(512))
    sidecar_original_title: Mapped[str | None] = mapped_column(String(512))
    sidecar_year: Mapped[int | None] = mapped_column(Integer)
    sidecar_overview: Mapped[str | None] = mapped_column(Text)
    sidecar_tmdb_id: Mapped[int | None] = mapped_column(Integer)
    sidecar_imdb_id: Mapped[str | None] = mapped_column(String(32))
    sidecar_tvdb_id: Mapped[int | None] = mapped_column(Integer)
    sidecar_source_path: Mapped[str | None] = mapped_column(Text)
    sidecar_poster_path: Mapped[str | None] = mapped_column(String(1024))
    sidecar_backdrop_path: Mapped[str | None] = mapped_column(String(1024))
    sidecar_metadata_status: Mapped[str | None] = mapped_column(String(32))
    local_poster_path: Mapped[str | None] = mapped_column(String(1024))
    local_backdrop_path: Mapped[str | None] = mapped_column(String(1024))
    local_logo_path: Mapped[str | None] = mapped_column(String(1024))
    match_source: Mapped[str | None] = mapped_column(String(64))
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
