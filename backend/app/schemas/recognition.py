from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RecognitionCorrectionCreate(BaseModel):
    corrected_title: str = Field(min_length=1, max_length=512)
    corrected_year: int | None = Field(default=None, ge=1900, le=2100)
    corrected_media_type: str | None = Field(default=None, max_length=32)
    removed_tokens: list[str] = Field(default_factory=list, max_length=32)
    confidence: float | None = Field(default=None, ge=0, le=1)


class RecognitionCorrectionRead(BaseModel):
    id: int
    media_item_id: int | None = None
    original_title: str | None = None
    previous_title: str | None = None
    corrected_title: str
    corrected_year: int | None = None
    corrected_media_type: str | None = None
    removed_tokens: list[str] = Field(default_factory=list)
    confidence: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecognitionTokenRuleRead(BaseModel):
    id: int
    token: str
    action: str
    source: str
    hit_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecognitionNormalizeResult(BaseModel):
    scan_session_id: int
    normalized_count: int
    skipped_count: int
    error_count: int


class NormalizedTitle(BaseModel):
    clean_title: str | None = None
    year: int | None = None
    media_type: str | None = None
    confidence: float | None = None
    junk_tokens: list[str] = Field(default_factory=list)
    explanation: str | None = None
    tmdb_queries: list[str] = Field(default_factory=list)


class LlmPreflightCheck(BaseModel):
    ok: bool
    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None
    duration_ms: int = 0
    response_valid_json: bool = False
    response_had_markdown: bool = False
    response_preview: str | None = None
    message: str | None = None
    error: str | None = None
    error_type: str | None = None
    human_message: str | None = None
    attempts: int = 1
    retryable: bool = False


class RecognitionPreflightResult(BaseModel):
    ok: bool
    local: LlmPreflightCheck
    cloud: LlmPreflightCheck
    cloud_fallback: LlmPreflightCheck | None = None
    warning: str | None = None
    message: str | None = None
