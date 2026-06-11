from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..models.enums import ReviewDecision


class TmdbManualSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    year: int | None = Field(default=None, ge=1900, le=2100)
    media_type: str = Field(default="movie", max_length=32)
    language: str = Field(default="ru-RU", max_length=16)


class TmdbManualLookupRequest(BaseModel):
    tmdb_id: int | None = Field(default=None, ge=1)
    imdb_id: str | None = Field(default=None, max_length=32)
    tvdb_id: int | None = Field(default=None, ge=1)
    media_type: str | None = Field(default=None, max_length=32)


class ReviewDecisionRequest(BaseModel):
    decision: ReviewDecision
    note: str | None = Field(default=None, max_length=2000)
    manual_title: str | None = Field(default=None, max_length=512)
    manual_year: int | None = Field(default=None, ge=1900, le=2100)
    manual_tmdb_id: int | None = Field(default=None, ge=1)
    manual_imdb_id: str | None = Field(default=None, max_length=32)
    manual_tvdb_id: int | None = Field(default=None, ge=1)
    manual_media_type: str | None = Field(default=None, max_length=32)


class TmdbManualLookupResponse(BaseModel):
    candidate_id: int
    warning: str | None = None


class BulkApproveRequest(BaseModel):
    scope: Literal["matched", "selected"]
    item_ids: list[int] | None = None

    @model_validator(mode="after")
    def validate_selected_scope(self) -> "BulkApproveRequest":
        if self.scope == "selected" and not self.item_ids:
            raise ValueError("item_ids is required when scope is 'selected'")
        return self


class BulkReviewDecisionRequest(BaseModel):
    item_ids: list[int] = Field(min_length=1)
    decision: Literal["approved", "ignored", "deferred"]
    note: str | None = Field(default=None, max_length=2000)


class BulkReviewResult(BaseModel):
    approved_count: int
    skipped_count: int
    ignored_count: int
    deferred_count: int
