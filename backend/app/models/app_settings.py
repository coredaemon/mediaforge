from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_api_key: Mapped[str | None] = mapped_column(Text)
    ai_provider: Mapped[str | None] = mapped_column(String(64))
    ai_api_key: Mapped[str | None] = mapped_column(Text)
    ai_base_url: Mapped[str | None] = mapped_column(Text)
    ai_model: Mapped[str | None] = mapped_column(String(256))
    cloud_ai_provider: Mapped[str | None] = mapped_column(String(64))
    cloud_ai_api_key: Mapped[str | None] = mapped_column(Text)
    cloud_ai_model: Mapped[str | None] = mapped_column(String(256))
    recognition_ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_source_path: Mapped[str | None] = mapped_column(Text)
    default_target_path: Mapped[str | None] = mapped_column(Text)
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
