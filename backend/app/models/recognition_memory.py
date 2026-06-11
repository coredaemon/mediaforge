from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class RecognitionCorrection(Base):
    __tablename__ = "recognition_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_item_id: Mapped[int] = mapped_column(ForeignKey("media_items.id"), index=True)
    original_title: Mapped[str | None] = mapped_column(String(512))
    previous_title: Mapped[str | None] = mapped_column(String(512))
    corrected_title: Mapped[str] = mapped_column(String(512))
    corrected_year: Mapped[int | None] = mapped_column(Integer)
    corrected_media_type: Mapped[str | None] = mapped_column(String(32))
    removed_tokens_json: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecognitionTokenRule(Base):
    __tablename__ = "recognition_token_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    action: Mapped[str] = mapped_column(String(32), default="remove", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
