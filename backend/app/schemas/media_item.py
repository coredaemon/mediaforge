from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import MediaItemStatus, MediaType


class MediaItemRead(BaseModel):
    id: int
    scan_session_id: int
    media_type: MediaType
    status: MediaItemStatus
    original_title: str | None = None
    parsed_title: str | None = None
    year: int | None = None
    season_number: int | None = None
    episode_number: int | None = None
    tmdb_id: int | None = None
    confidence: float | None = None
    needs_review: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
