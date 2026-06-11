from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class ProcessedMediaRecord(Base):
    __tablename__ = "processed_media_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_recognized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source_path: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    file_stem: Mapped[str | None] = mapped_column(String(512))
    file_extension: Mapped[str | None] = mapped_column(String(32))
    file_size: Mapped[int | None] = mapped_column(Integer)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_fingerprint: Mapped[str | None] = mapped_column(String(128))
    file_identity_key: Mapped[str] = mapped_column(String(1024), unique=True, index=True)

    media_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32))

    clean_title: Mapped[str | None] = mapped_column(String(512))
    year: Mapped[int | None] = mapped_column(Integer)
    season: Mapped[int | None] = mapped_column(Integer)
    episode: Mapped[int | None] = mapped_column(Integer)
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    tmdb_media_type: Mapped[str | None] = mapped_column(String(32))
    matched_title: Mapped[str | None] = mapped_column(String(512))
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
    match_source: Mapped[str | None] = mapped_column(String(64))
    sidecar_source_path: Mapped[str | None] = mapped_column(Text)
    local_poster_path: Mapped[str | None] = mapped_column(String(1024))
    local_backdrop_path: Mapped[str | None] = mapped_column(String(1024))

    scan_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    recognition_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_session_id: Mapped[int | None] = mapped_column(Integer)
    last_media_item_id: Mapped[int | None] = mapped_column(Integer)
