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

The current backend can create scan sessions, discover files in a local source directory, record them in SQLite, parse video filenames into first-pass `MediaItem` candidates, match those candidates against TMDB, and return the result through the API. Discovery, parsing, and matching are read-only: they do not move, delete, or modify media files.

## Quick Start

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
pytest
python -m backend.scripts.init_db
uvicorn backend.app.main:app --reload
```

The health endpoint is available at `GET /health`.

## Backend Commands

Install dependencies:

```bash
pip install -e ".[dev]"
```

Initialize the local SQLite database:

```bash
python -m backend.scripts.init_db
```

Run the backend:

```bash
uvicorn backend.app.main:app --reload
```

Check health:

```bash
curl http://127.0.0.1:8000/health
```

Create a scan session:

```bash
curl -X POST http://127.0.0.1:8000/scan-sessions ^
  -H "Content-Type: application/json" ^
  -d "{\"source_path\":\"D:/Media/Inbox\",\"target_path\":\"D:/Media/Library\"}"
```

Run discovery for a scan session:

```bash
curl -X POST http://127.0.0.1:8000/scan-sessions/1/discover
```

Parse discovered video files:

```bash
curl -X POST http://127.0.0.1:8000/scan-sessions/1/parse
```

List discovered files:

```bash
curl http://127.0.0.1:8000/scan-sessions/1/files
```

List parsed media item candidates:

```bash
curl http://127.0.0.1:8000/scan-sessions/1/items
```

Run TMDB matching:

```bash
curl -X POST http://127.0.0.1:8000/scan-sessions/1/match-tmdb
```

List TMDB candidates for an item:

```bash
curl http://127.0.0.1:8000/items/1/tmdb-candidates
```

## Local Workflow

1. Initialize the DB with `python -m backend.scripts.init_db`.
2. Start the backend with `uvicorn backend.app.main:app --reload`.
3. Create a scan session with `POST /scan-sessions`.
4. Discover source files with `POST /scan-sessions/{id}/discover`.
5. Parse video filenames with `POST /scan-sessions/{id}/parse`.
6. Match parsed candidates with `POST /scan-sessions/{id}/match-tmdb`.
7. Inspect discovered files with `GET /scan-sessions/{id}/files`.
8. Inspect parsed items with `GET /scan-sessions/{id}/items`.
9. Inspect TMDB candidates with `GET /items/{item_id}/tmdb-candidates`.

## TMDB Key

TMDB API keys are local-only. Put a real key in your local `.env` file:

```bash
TMDB_API_KEY=
```

Never commit `.env` or real provider keys. The committed `.env.example` intentionally contains placeholders only. If matching is requested without `TMDB_API_KEY`, the API returns `400 TMDB_API_KEY is not configured`.
