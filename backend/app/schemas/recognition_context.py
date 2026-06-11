from pydantic import BaseModel, Field


class RecognitionContext(BaseModel):
    folder_name: str | None = None
    sidecar_title: str | None = None
    sidecar_year: int | None = None
    sidecar_overview: str | None = None
    sidecar_tmdb_id: int | None = None
    sidecar_imdb_id: str | None = None
    sidecar_tvdb_id: int | None = None
    sidecar_source_path: str | None = None
    local_poster_path: str | None = None
    local_backdrop_path: str | None = None
    memory_tmdb_id: int | None = None
    memory_imdb_id: str | None = None
    memory_tvdb_id: int | None = None
    failed_tmdb_queries: list[str] = Field(default_factory=list)
    language_preference: str = "ru-RU"
