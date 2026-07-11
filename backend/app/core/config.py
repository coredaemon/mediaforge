from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "mediaforge.local.sqlite3"


def _default_database_url() -> str:
    return f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


class Settings(BaseSettings):
    environment: str = Field(default="development", alias="MEDIAFORGE_ENV")
    database_url: str = Field(
        default_factory=_default_database_url,
        alias="MEDIAFORGE_DATABASE_URL",
    )
    tmdb_api_key: str = Field(default="", alias="TMDB_API_KEY")
    ai_provider: str = Field(default="", alias="AI_PROVIDER")
    ai_api_key: str = Field(default="", alias="AI_API_KEY")
    ai_base_url: str = Field(default="", alias="AI_BASE_URL")
    ai_model: str = Field(default="", alias="AI_MODEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
