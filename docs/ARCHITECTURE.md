# Architecture

MediaForge is a local-first web application with a Python/FastAPI backend, SQLite database, and a React/TypeScript web UI.

## Layers

- **FastAPI API layer** exposes HTTP endpoints and delegates all workflow decisions to services.
- **Service layer** coordinates application use cases: scanning, parsing, planning, settings, filesystem browsing.
- **Repository layer** owns database reads and writes behind explicit interfaces.
- **SQLite database** stores local application state, materialized operation plans, and app settings.
- **Scanner** discovers candidate media files without modifying the filesystem.
- **Parser** turns filenames and folder context into structured candidates.
- **TMDB Client** resolves confirmed matches against the canonical metadata source.
- **Planner** builds dry-run operation plans for preview.
- **Settings** stores local configuration including API keys — never committed to git.
- **Filesystem Service** provides read-only directory browsing for the UI folder picker.
- **Web UI** provides a Russian-language local browser interface for running and inspecting the pipeline.
- **Apply Engine** — not implemented yet.
- **Rollback Engine** — not implemented yet.

## Pipeline

```text
DISCOVERED -> PARSED -> MATCHED -> PLANNED -> READY_TO_APPLY -> APPLYING -> COMPLETED
                                                                  \-> FAILED
                                                                  \-> ROLLED_BACK
```

The pipeline is intentionally staged: discovery and planning can be inspected before any filesystem changes are attempted.

## Current Models

- `ScanSession` stores source and target paths, lifecycle status, timestamps, and errors.
- `MediaFile` stores discovered file paths, names, extensions, sizes, classification, and scan errors.
- `MediaItem` stores parsed movie, TV episode, or unknown local candidates.
- `TmdbMatchCandidate` stores TMDB search results scored against a parsed candidate.
- `OperationPlan` stores a materialized dry-run plan for a scan session.
- `PlanOperation` stores one planned action: `CREATE_DIR`, `MOVE_FILE`, `WRITE_TEXT_FILE`, or `DOWNLOAD_FILE`.
- `AppSettings` stores local configuration: API keys, AI provider settings, default paths, setup state.

## Current Scanner Flow

1. Load the `ScanSession` from SQLite.
2. Validate that `source_path` exists and is a directory.
3. Mark the session as `DISCOVERING`.
4. Walk the source directory and classify files as `VIDEO`, `SUBTITLE`, `SIDECAR`, or `OTHER`.
5. Store each discovered file in `MediaFile`.
6. Mark the session as `DISCOVERED`, or `FAILED` for critical errors.

## Current Parser Flow

1. Load the `ScanSession`.
2. Select discovered `VIDEO` files.
3. Parse filenames using local rules for movie years and TV episode patterns.
4. Remove common technical tokens.
5. Create one `MediaItem` candidate per unlinked video file.
6. Link each parsed video `MediaFile` to its `MediaItem`.
7. Mark the session as `PARSED`.

## Current TMDB Matching Flow

1. Load parsed `MediaItem` rows for a scan session.
2. Resolve TMDB API key: check `AppSettings.tmdb_api_key` first, then `TMDB_API_KEY` env var.
3. Search TMDB and score candidates.
4. Auto-select best candidate when `score >= 0.80`.
5. Mark uncertain candidates as `NEEDS_REVIEW`, items with no results as `UNMATCHED`.

## Dry-run Planning Layer

Planning is separated from apply. The planner reads `MATCHED` items and builds a `OperationPlan` with `PlanOperation` rows stored in SQLite. No filesystem changes happen.

Operations created per item:
- `CREATE_DIR` — target folder to create
- `MOVE_FILE` — source video → target library path
- `WRITE_TEXT_FILE` — future `.nfo` metadata file
- `DOWNLOAD_FILE` — future poster/backdrop artwork

Target paths follow library conventions:
- Movies: `{target}/Movies/{Title} ({Year})/{Title} ({Year}){ext}`
- TV episodes: `{target}/TV Shows/{Title}/Season 01/{Title} S01E01{ext}`

Apply and rollback are not implemented yet.

## App Settings

`AppSettings` is a single-row singleton table (id=1). It stores:
- `tmdb_api_key` — encrypted at rest by OS; never returned in `GET /settings` response
- `ai_provider`, `ai_api_key`, `ai_base_url`, `ai_model`
- `default_source_path`, `default_target_path`
- `setup_completed` — drives the setup wizard flow

`GET /settings` returns only safe fields: `tmdb_configured: bool`, `ai_configured: bool`, etc.

## Local Secrets Policy

- API keys and tokens are stored only in `mediaforge.local.sqlite3` (git-ignored) or `.env` (git-ignored).
- `GET /settings` never exposes raw key values.
- `.env.example` contains only empty placeholder values.
- No secrets, user-specific paths, or media files are ever committed.

## Filesystem Browser

`GET /filesystem/roots` — returns available drives on Windows, `/` and home on Unix.
`GET /filesystem/browse?path=...` — returns directory entries for a given path.

The filesystem service is read-only: it lists directories only, never modifies, moves, copies, or deletes anything.

## Setup Wizard

On first launch, the React app calls `GET /settings` and checks `setup_completed`. If `false`, the user is redirected to `/setup` where a 5-step wizard guides through TMDB key, AI provider, and default folders configuration. On completion, `PUT /settings` is called with `setup_completed: true`.

The "Настройки" button in the header always allows returning to the wizard for editing.

## Safe Preview Mode

The entire current UI communicates to users that no files are modified. The session detail page shows a persistent notice: "MediaForge работает в безопасном режиме preview. Файлы не перемещаются и не изменяются."

Apply and rollback workflows are not implemented yet.

## Web UI Layer

Frontend is a Vite + React + TypeScript app in `frontend/`. It:
- communicates with the backend API via `frontend/src/api.ts`
- is fully Russian-language (`frontend/src/i18n.ts`)
- uses a folder picker component backed by `/filesystem/browse` and `/filesystem/roots`
- auto-populates session creation form from `default_source_path` / `default_target_path` settings
- shows backend health indicator in the header

## Review Flow

The session detail page is now a review/preview workspace rather than a raw database table. The main action is **Начать анализ**, which runs discovery, parsing, TMDB matching, and dry-run planning in order. Manual step buttons remain available under **Ручной режим** for debugging or reruns.

The UI summarizes loaded files, items, plans, and operations: total files, video files, subtitles, parsed media items, TMDB matches, items that need review, and planned operations.

Raw enums are translated into Russian labels and displayed as status badges. Technical tables are still available, but they are moved behind **Технические детали** so the primary screen reads as a human review flow.

## Human-In-The-Loop Matching

TMDB matching creates candidates first and only auto-selects confident matches. Users can inspect candidates for any media item and manually select one through:

`POST /items/{item_id}/tmdb-candidates/{candidate_id}/select`

Candidate selection is handled in the service layer. It validates item and candidate ownership, clears previous selected candidates for the item, marks the chosen candidate as selected, and updates `MediaItem` with `tmdb_id`, `tmdb_media_type`, `matched_title`, `matched_year`, `match_confidence`, `status = MATCHED`, and `needs_review = false`.

## Planning After Manual Selection

When a user changes the selected TMDB candidate, the existing dry-run plan may no longer reflect the chosen metadata. The UI provides **Пересобрать план**, which calls:

`POST /scan-sessions/{id}/plan?force=true`

This replaces the current draft/ready plan and reloads operations. It still does not apply anything to the filesystem.
