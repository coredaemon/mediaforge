from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TmdbMatchCandidateRead(BaseModel):
    id: int
    media_item_id: int
    tmdb_id: int
    media_type: str
    title: str
    original_title: str | None = None
    overview: str | None = None
    release_date: str | None = None
    first_air_date: str | None = None
    year: int | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    wikidata_id: str | None = None
    metadata_language: str | None = None
    overview_is_fallback: bool = False
    vote_average: float | None = None
    popularity: float | None = None
    score: float
    is_selected: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TmdbMatchResult(BaseModel):
    scan_session_id: int
    matched_count: int
    needs_review_count: int
    unmatched_count: int
    skipped_count: int


class TmdbSearchResult(BaseModel):
    tmdb_id: int
    media_type: str
    title: str
    original_title: str | None = None
    overview: str | None = None
    release_date: str | None = None
    first_air_date: str | None = None
    year: int | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    vote_average: float | None = None
    popularity: float | None = None
    raw_json: dict[str, Any] | None = None


class TmdbExternalIds(BaseModel):
    imdb_id: str | None = None
    tvdb_id: int | None = None
    wikidata_id: str | None = None


class TmdbDetailsResult(BaseModel):
    tmdb_id: int
    media_type: str
    title: str
    original_title: str | None = None
    overview: str | None = None
    year: int | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    external_ids: TmdbExternalIds = TmdbExternalIds()
    metadata_language: str = "ru-RU"
    overview_is_fallback: bool = False


class TmdbEpisodeResult(BaseModel):
    tmdb_episode_id: int | None = None
    season_number: int
    episode_number: int
    title: str | None = None
    overview: str | None = None
    air_date: str | None = None


class TmdbSeasonDetailsResult(BaseModel):
    tmdb_season_id: int | None = None
    season_number: int
    title: str | None = None
    overview: str | None = None
    poster_path: str | None = None
    poster_url: str | None = None
    episodes: list[TmdbEpisodeResult] = []
    metadata_language: str = "ru-RU"
