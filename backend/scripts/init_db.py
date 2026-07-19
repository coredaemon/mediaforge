import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.app.db.base import Base, import_models
from backend.app.db.session import engine

logger = logging.getLogger(__name__)

# Columns that were added to existing tables after the initial schema.
# Format: (table, column, sqlite_type, nullable_default)
_COLUMN_MIGRATIONS: list[tuple[str, str, str, str]] = [
    ("media_items", "tmdb_media_type", "VARCHAR(32)", ""),
    ("media_items", "matched_title", "VARCHAR(512)", ""),
    ("media_items", "matched_year", "INTEGER", ""),
    ("media_items", "match_confidence", "FLOAT", ""),
    ("media_items", "ai_clean_title", "VARCHAR(512)", ""),
    ("media_items", "ai_year", "INTEGER", ""),
    ("media_items", "ai_media_type", "VARCHAR(32)", ""),
    ("media_items", "ai_confidence", "FLOAT", ""),
    ("media_items", "ai_junk_tokens", "JSON", ""),
    ("media_items", "ai_explanation", "TEXT", ""),
    ("media_items", "gemini_clean_title", "VARCHAR(512)", ""),
    ("media_items", "gemini_year", "INTEGER", ""),
    ("media_items", "gemini_media_type", "VARCHAR(32)", ""),
    ("media_items", "gemini_confidence", "FLOAT", ""),
    ("media_items", "gemini_junk_tokens", "JSON", ""),
    ("media_items", "gemini_explanation", "TEXT", ""),
    ("media_items", "tmdb_queries", "JSON", ""),
    ("media_items", "local_ai_status", "VARCHAR(32)", ""),
    ("media_items", "local_ai_duration_ms", "INTEGER", ""),
    ("media_items", "local_ai_error", "TEXT", ""),
    ("media_items", "local_ai_response_valid_json", "BOOLEAN", ""),
    ("media_items", "local_ai_model", "VARCHAR(256)", ""),
    ("media_items", "gemini_status", "VARCHAR(32)", ""),
    ("media_items", "gemini_duration_ms", "INTEGER", ""),
    ("media_items", "gemini_error", "TEXT", ""),
    ("media_items", "gemini_response_valid_json", "BOOLEAN", ""),
    ("media_items", "gemini_model", "VARCHAR(256)", ""),
    ("app_settings", "cloud_ai_provider", "VARCHAR(64)", ""),
    ("app_settings", "cloud_ai_api_key", "TEXT", ""),
    ("app_settings", "cloud_ai_base_url", "TEXT", ""),
    ("app_settings", "cloud_ai_model", "VARCHAR(256)", ""),
    ("app_settings", "recognition_ai_enabled", "BOOLEAN", "DEFAULT 1"),
    ("media_files", "modified_at", "DATETIME", ""),
    ("media_files", "reused_from_memory", "BOOLEAN", "DEFAULT 0"),
    ("media_items", "imdb_id", "VARCHAR(32)", ""),
    ("media_items", "tvdb_id", "INTEGER", ""),
    ("media_items", "wikidata_id", "VARCHAR(64)", ""),
    ("media_items", "localized_title", "VARCHAR(512)", ""),
    ("media_items", "localized_overview", "TEXT", ""),
    ("media_items", "tmdb_original_title", "VARCHAR(512)", ""),
    ("media_items", "poster_path", "VARCHAR(512)", ""),
    ("media_items", "backdrop_path", "VARCHAR(512)", ""),
    ("media_items", "poster_url", "VARCHAR(1024)", ""),
    ("media_items", "backdrop_url", "VARCHAR(1024)", ""),
    ("media_items", "metadata_language", "VARCHAR(16)", ""),
    ("media_items", "reused_from_memory", "BOOLEAN", "DEFAULT 0"),
    ("media_items", "memory_status", "VARCHAR(32)", ""),
    ("tmdb_match_candidates", "poster_url", "VARCHAR(1024)", ""),
    ("tmdb_match_candidates", "backdrop_url", "VARCHAR(1024)", ""),
    ("tmdb_match_candidates", "imdb_id", "VARCHAR(32)", ""),
    ("tmdb_match_candidates", "tvdb_id", "INTEGER", ""),
    ("tmdb_match_candidates", "wikidata_id", "VARCHAR(64)", ""),
    ("tmdb_match_candidates", "metadata_language", "VARCHAR(16)", ""),
    ("tmdb_match_candidates", "overview_is_fallback", "BOOLEAN", "DEFAULT 0"),
    ("media_items", "review_decision", "VARCHAR(32)", "DEFAULT 'pending'"),
    ("media_items", "reviewed_at", "DATETIME", ""),
    ("media_items", "review_note", "TEXT", ""),
    ("media_items", "manual_title", "VARCHAR(512)", ""),
    ("media_items", "manual_year", "INTEGER", ""),
    ("media_items", "manual_tmdb_id", "INTEGER", ""),
    ("media_items", "manual_imdb_id", "VARCHAR(32)", ""),
    ("media_items", "manual_tvdb_id", "INTEGER", ""),
    ("media_items", "manual_media_type", "VARCHAR(32)", ""),
    ("app_settings", "cloud_ai_fallback_provider", "VARCHAR(64)", ""),
    ("app_settings", "cloud_ai_fallback_api_key", "TEXT", ""),
    ("app_settings", "cloud_ai_fallback_model", "VARCHAR(256)", ""),
    ("app_settings", "openrouter_api_key", "TEXT", ""),
    ("app_settings", "openrouter_base_url", "TEXT", ""),
    ("app_settings", "openrouter_fast_chain", "TEXT", ""),
    ("app_settings", "openrouter_smart_chain", "TEXT", ""),
    ("app_settings", "openrouter_last_models_cache", "TEXT", ""),
    ("media_items", "sidecar_title", "VARCHAR(512)", ""),
    ("media_items", "sidecar_original_title", "VARCHAR(512)", ""),
    ("media_items", "sidecar_year", "INTEGER", ""),
    ("media_items", "sidecar_overview", "TEXT", ""),
    ("media_items", "sidecar_tmdb_id", "INTEGER", ""),
    ("media_items", "sidecar_imdb_id", "VARCHAR(32)", ""),
    ("media_items", "sidecar_tvdb_id", "INTEGER", ""),
    ("media_items", "sidecar_source_path", "TEXT", ""),
    ("media_items", "sidecar_poster_path", "VARCHAR(1024)", ""),
    ("media_items", "sidecar_backdrop_path", "VARCHAR(1024)", ""),
    ("media_items", "sidecar_metadata_status", "VARCHAR(32)", ""),
    ("media_items", "local_poster_path", "VARCHAR(1024)", ""),
    ("media_items", "local_backdrop_path", "VARCHAR(1024)", ""),
    ("media_items", "local_logo_path", "VARCHAR(1024)", ""),
    ("media_items", "match_source", "VARCHAR(64)", ""),
    ("processed_media_records", "match_source", "VARCHAR(64)", ""),
    ("processed_media_records", "sidecar_source_path", "TEXT", ""),
    ("processed_media_records", "local_poster_path", "VARCHAR(1024)", ""),
    ("processed_media_records", "local_backdrop_path", "VARCHAR(1024)", ""),
    ("processed_media_records", "tv_show_title", "VARCHAR(512)", ""),
    ("processed_media_records", "tv_season_number", "INTEGER", ""),
    ("processed_media_records", "tv_episode_number", "INTEGER", ""),
    ("processed_media_records", "tmdb_show_id", "INTEGER", ""),
    ("processed_media_records", "tmdb_episode_id", "INTEGER", ""),
    ("plan_operations", "validation_status", "VARCHAR(32)", "DEFAULT 'pending'"),
    ("plan_operations", "validation_error", "TEXT", ""),
    ("plan_operations", "validated_at", "DATETIME", ""),
    ("tv_episodes", "review_acknowledged", "BOOLEAN", "DEFAULT 0"),
]


async def _apply_column_migrations(conn: AsyncConnection) -> None:
    """Add missing columns to existing tables (idempotent)."""
    for table, column, col_type, _default in _COLUMN_MIGRATIONS:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing_cols = {row[1] for row in result.fetchall()}
        if column not in existing_cols:
            default_sql = f" {_default}" if _default else ""
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_sql}"))
            logger.info("Migration: added column %s.%s", table, column)


async def init_db() -> None:
    import_models()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _apply_column_migrations(connection)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_db())
