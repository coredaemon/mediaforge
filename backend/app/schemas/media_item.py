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
    tmdb_media_type: str | None = None
    matched_title: str | None = None
    matched_year: int | None = None
    match_confidence: float | None = None
    ai_clean_title: str | None = None
    ai_year: int | None = None
    ai_media_type: str | None = None
    ai_confidence: float | None = None
    ai_junk_tokens: list[str] | None = None
    ai_explanation: str | None = None
    gemini_clean_title: str | None = None
    gemini_year: int | None = None
    gemini_media_type: str | None = None
    gemini_confidence: float | None = None
    gemini_junk_tokens: list[str] | None = None
    gemini_explanation: str | None = None
    tmdb_queries: list[str] | None = None
    local_ai_status: str | None = None
    local_ai_duration_ms: int | None = None
    local_ai_error: str | None = None
    local_ai_response_valid_json: bool | None = None
    local_ai_model: str | None = None
    gemini_status: str | None = None
    gemini_duration_ms: int | None = None
    gemini_error: str | None = None
    gemini_response_valid_json: bool | None = None
    gemini_model: str | None = None
    confidence: float | None = None
    needs_review: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
