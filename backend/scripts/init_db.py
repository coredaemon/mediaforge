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
]


async def _apply_column_migrations(conn: AsyncConnection) -> None:
    """Add missing columns to existing tables (idempotent)."""
    for table, column, col_type, _default in _COLUMN_MIGRATIONS:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing_cols = {row[1] for row in result.fetchall()}
        if column not in existing_cols:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            logger.info("Migration: added column %s.%s", table, column)


async def init_db() -> None:
    import_models()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _apply_column_migrations(connection)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_db())
