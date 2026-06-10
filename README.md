# MediaForge

MediaForge is a local-first media library organizer for movies and TV shows. It is intended to help prepare local libraries for Jellyfin, Plex, and Kodi by scanning folders, parsing messy file names, matching metadata, previewing safe changes, applying approved operations, and supporting rollback.

This repository is public. Real API keys, tokens, user-specific settings, local database files, logs, caches, absolute user paths, and media files must never be committed. Use `.env.example` only as a placeholder template and keep real secrets in a local `.env` file outside version control.

## Development Plan

The first implementation path is:

1. Scan local folders.
2. Parse movie and episode candidates.
3. Match confirmed candidates against TMDB as the canonical metadata source.
4. Build a dry-run operation plan.
5. Preview and safely apply approved file operations.
6. Roll back applied operations when needed.

This initial commit only establishes the project structure, configuration, health endpoint, database session foundation, path utilities, documentation, and tests.

## Quick Start

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
pytest
uvicorn backend.app.main:app --reload
```

The health endpoint is available at `GET /health`.
