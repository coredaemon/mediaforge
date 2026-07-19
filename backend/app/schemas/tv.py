from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TvEpisodeRead(BaseModel):
    id: int
    show_id: int
    season_id: int | None = None
    source_file_id: int | None = None
    season_number: int
    episode_number: int
    absolute_number: int | None = None
    title: str | None = None
    overview: str | None = None
    air_date: str | None = None
    tmdb_episode_id: int | None = None
    source_path: str | None = None
    target_path: str | None = None
    confidence: float | None = None
    needs_review: bool = False
    review_acknowledged: bool = False
    issue: str | None = None
    warning: str | None = None
    match_source: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TvSeasonRead(BaseModel):
    id: int
    show_id: int
    season_number: int
    title: str | None = None
    tmdb_season_id: int | None = None
    episode_count: int | None = None
    poster_path: str | None = None
    poster_url: str | None = None
    episodes: list[TvEpisodeRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TvShowRead(BaseModel):
    id: int
    scan_session_id: int
    local_group_id: str | None = None
    title: str
    original_title: str | None = None
    year: int | None = None
    first_air_date: str | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    wikidata_id: str | None = None
    overview: str | None = None
    poster_path: str | None = None
    poster_url: str | None = None
    backdrop_path: str | None = None
    backdrop_url: str | None = None
    language: str | None = None
    match_source: str | None = None
    confidence: float | None = None
    review_decision: str
    needs_review: bool
    ai_reasoning_summary: str | None = None
    warnings: list[str] | None = None
    seasons: list[TvSeasonRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TvAnalyzeResult(BaseModel):
    scan_session_id: int
    show_count: int
    season_count: int
    episode_count: int
    warning_count: int


class TvManualSearchRequest(BaseModel):
    query: str
    year: int | None = None


class TvManualLookupRequest(BaseModel):
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    select: bool = False


class TvReviewDecisionRequest(BaseModel):
    decision: str
    note: str | None = None
    manual_title: str | None = None
    manual_year: int | None = None
    manual_tmdb_id: int | None = None
    manual_imdb_id: str | None = None
    manual_tvdb_id: int | None = None


class TvFolderFileHint(BaseModel):
    relative_path: str
    file_name: str
    kind: str
    size_bytes: int | None = None
    modified_at: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    possible_title: str | None = None
    sidecar_ids: dict[str, Any] | None = None


class TvFolderContext(BaseModel):
    root_path: str
    folders: list[str]
    files: list[TvFolderFileHint]
    possible_show_titles: list[str]
    warnings: list[str] = []
    truncated: bool = False
