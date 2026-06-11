from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AppSettingsRead(BaseModel):
    """Safe view: no raw API keys are included."""

    tmdb_configured: bool
    ai_configured: bool
    ai_provider: str | None
    ai_base_url: str | None
    ai_model: str | None
    cloud_ai_configured: bool
    cloud_ai_provider: str | None
    cloud_ai_model: str | None
    recognition_ai_enabled: bool
    default_source_path: str | None
    default_target_path: str | None
    setup_completed: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=False)


class AppSettingsUpdate(BaseModel):
    tmdb_api_key: str | None = None
    ai_provider: str | None = None
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    cloud_ai_provider: str | None = None
    cloud_ai_api_key: str | None = None
    cloud_ai_model: str | None = None
    recognition_ai_enabled: bool | None = None
    default_source_path: str | None = None
    default_target_path: str | None = None
    setup_completed: bool | None = None


class TestConnectionResult(BaseModel):
    success: bool
    message: str


class LocalModelsResult(BaseModel):
    success: bool
    models: list[str]
    message: str | None = None


class DirectoryEntry(BaseModel):
    name: str
    path: str


class BrowseResult(BaseModel):
    current_path: str
    parent_path: str | None
    directories: list[DirectoryEntry]
    readable: bool
    error: str | None = None
