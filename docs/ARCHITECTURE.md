# Architecture

MediaForge is a local-first web application with a Python/FastAPI backend, SQLite database, and a React/TypeScript web UI.

## Layers

- **FastAPI API layer** exposes HTTP endpoints and delegates all workflow decisions to services.
- **Service layer** coordinates application use cases: scanning, parsing, planning, settings, filesystem browsing.
- **Repository layer** owns database reads and writes behind explicit interfaces.
- **SQLite database** stores local application state, materialized operation plans, and app settings.
- **Scanner** discovers candidate media files without modifying the filesystem.
- **Parser** turns filenames and folder context into structured candidates.
- **Recognition Memory** stores manual corrections and reusable token rules for future scans.
- **AI Normalization** can use a local model first and Gemini fallback later to clean noisy release names before TMDB search.
- **TMDB Client** resolves confirmed matches against the canonical metadata source.
- **Planner** builds dry-run operation plans for preview.
- **Settings** stores local configuration including API keys — never committed to git.
- **Filesystem Service** provides read-only directory browsing for the UI folder picker.
- **Web UI** provides a Russian-language local browser interface for running and inspecting the pipeline.
- **Apply Engine** — validates and applies `READY` plans sequentially with logging.
- **Rollback Engine** — not implemented yet (apply logs include `rollback_data`).

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
- `RecognitionCorrection` stores user-approved title/year/media-type corrections.
- `RecognitionTokenRule` stores reusable cleanup rules such as release groups or junk tokens to remove.
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
3. Build a priority query list: manual/AI `tmdb_queries`, Gemini title, local AI title, parser title, original filename.
4. Search TMDB and score candidates against the query that returned results.
5. Auto-select best candidate when `score >= 0.80`.
6. Mark uncertain candidates as `NEEDS_REVIEW`, items with no results as `UNMATCHED`.

## AI-Assisted Recognition Flow

The current recognition pipeline is:

```text
LLM Preflight -> Discovery -> Deterministic parser -> Local LLM normalization -> TMDB search pass #1
          -> Gemini fallback -> TMDB search pass #2 -> Human review -> Recognition Memory
```

Implemented endpoints:
- `POST /recognition/preflight`
- `POST /scan-sessions/{id}/normalize-local-ai`
- `POST /scan-sessions/{id}/resolve-with-gemini`
- `POST /items/{item_id}/corrections`
- `GET /recognition-memory/corrections`
- `GET /recognition-memory/token-rules`

`/recognition/preflight` sends real generation requests to the configured local LLM and Gemini cloud fallback. It validates that the model returns JSON with `ok: true`, the expected provider (`local` or `gemini`), and `test: "mediaforge-preflight"`. If AI-assisted recognition is enabled and either side fails, the UI stops the analysis before discovery/parse/TMDB and shows the failed provider, duration, model, error type, JSON validity, and sanitized response preview. API keys are never included in responses or logs.

Local AI normalization reads `AppSettings.ai_provider`, `ai_base_url`, `ai_model`, and `ai_api_key` when needed. Cloud fallback reads `cloud_ai_provider`, `cloud_ai_base_url`, `cloud_ai_model`, and `cloud_ai_api_key`. Supported clients are Ollama, LM Studio/OpenAI-compatible endpoints, custom OpenAI-compatible endpoints, Gemini, and OpenAI/ChatGPT-compatible cloud providers. API keys are passed only to outgoing requests and are never returned by read endpoints.

Cloud model discovery is provider-backed:
- Gemini uses the Gemini models API and returns models that support `generateContent`.
- OpenAI/ChatGPT-compatible providers use `/v1/models`.
- Custom OpenAI-compatible providers can use the configured `cloud_ai_base_url`; if discovery is unsupported, the UI still allows manual model input for custom only.

Secret handling rejects empty strings and known placeholders such as `MediaOrganizer_API_Key`, `YOUR_API_KEY`, and `PASTE_API_KEY_HERE`. HTTP errors are sanitized before they are returned to the UI so query parameters such as `key=...` and bearer tokens are redacted.

### Cloud AI retry and fallback

Cloud recognition and preflight use `post_with_retry` for Gemini and OpenAI-compatible cloud clients (when an API key is present). Retryable conditions: HTTP `429`, `500`, `502`, `503`, `504`, network timeouts, and connection errors. Up to 3 attempts with 1s and 2s backoff. Non-retryable: `400`, `401`, `403`, `404`, and JSON validation failures after a response is received.

Preflight decision: `ok = local_ok AND (primary_cloud_ok OR fallback_cloud_ok)`. If primary fails temporarily and fallback succeeds, the pipeline continues with a warning. If both cloud models fail, analysis stops with a Russian human-readable message. Technical error text is stored separately from `human_message` for the UI details panel.

Error classification (`error_type`): `temporary_unavailable`, `rate_limited`, `auth_error`, `model_not_found`, `timeout`, `connection_error`, `not_configured`, `invalid_json`.

Manual corrections update the media item, save a correction row, and upsert remove-token rules. Token rules are applied on later normalization passes so names like release groups, streaming tags, and team names can be removed consistently.

Each `MediaItem` stores recognition diagnostics for local AI and Gemini: status (`not_run`, `success`, `failed`, `skipped`), duration, model, JSON validity, and sanitized error text. The UI shows these diagnostics next to parser/AI/Gemini titles and TMDB query priorities.

AI response normalization (`backend/app/utils/ai_response_normalization.py`) coerces common LLM output variants before validation:
- `tmdb_queries`: accepts `list[str]`, `list[dict]`, single `dict`, `str`, or `null` with fallbacks from `clean_title`/`year`/parser title
- `media_type`: maps aliases such as `movie`, `film`, `фильм` to internal enum values
- `confidence`: accepts `0.9`, `90`, `"90%"`, clamps to `0..1`
- `junk_tokens`: accepts comma-separated strings or arrays

If coercion was required, the item still gets `success` status and a short warning is stored for the UI; only unparseable JSON or responses without a usable title are marked `failed`.

## Processed Media Memory

`ProcessedMediaRecord` is session-independent SQLite memory keyed by `file_identity_key = file_name|size|modified_at`.

Reuse flow:
1. `ScannerService` stores `size_bytes` and `modified_at` on each `MediaFile`.
2. `ParserService` looks up an existing record before creating a new `MediaItem`.
3. If the file identity matches, the item is marked `reused_from_memory=true` and previous recognition/TMDB metadata is restored.
4. `RecognitionService` and `TMDBService` skip reused items unless `force=true`.
5. After a successful TMDB match or manual candidate selection, `ProcessedMediaService.record_from_item()` upserts the record.

Changed files (different size or mtime) are treated as new items (`memory_status=new`).

## TMDB Localization and External IDs

Search uses `language=ru-RU` with fallback to `en-US` when no Russian results are returned. Details requests use:

```text
/movie/{id}?language=ru-RU&append_to_response=external_ids,images,translations
/tv/{id}?language=ru-RU&append_to_response=external_ids,images,translations
```

Images prefer `include_image_language=ru,null,en`. External IDs (`imdb_id`, `tvdb_id`, `wikidata_id`) are stored on `MediaItem`, `TmdbMatchCandidate`, and `ProcessedMediaRecord` for future Jellyfin/Plex/Kodi NFO export.

## Visual TMDB Review

`GET /items/{id}/tmdb-candidates` returns enriched candidate cards (poster/backdrop URLs, localized overview, external IDs, metadata language). If a reused memory item has no DB candidates, the API synthesizes a single selected card from stored item metadata. The session UI renders visual candidate cards and matched-item cards with posters and IDs.

## Dry-run Planning Layer

Planning is separated from apply. The planner reads `MATCHED` items and builds a `OperationPlan` with `PlanOperation` rows stored in SQLite. No filesystem changes happen.

Operations created per item:
- `CREATE_DIR` — target folder to create
- `MOVE_FILE` — source video → target library path
- `WRITE_TEXT_FILE` — future `.nfo` metadata file
- `DOWNLOAD_FILE` — future poster/backdrop artwork

Target paths follow library conventions:
- Movies: `{target}/{Title} ({Year})/{Title} ({Year}){ext}` (no automatic `Movies` subfolder; `{target}` is the user-selected destination root)
- TV episodes: `{target}/TV Shows/{Title}/Season 01/{Title} S01E01{ext}`

## Apply Flow

```
preview (plan) → validate → user confirm → apply → apply_run logs → (future rollback)
```

1. **Planning** builds a `READY` plan with `PENDING` operations.
2. **Validation** (`PlanValidationService`) marks each `PlanOperation` with `validation_status`: `pending`, `ok`, `warning`, or `conflict`.
3. **Apply** (`ApplyService`) requires `confirm=true`, re-validates, then executes operations sequentially.
4. Each apply creates an `ApplyRun` and `ApplyOperationLog` rows with rollback metadata (e.g. move from/to paths).

Plan statuses: `DRAFT`, `READY`, `APPLYING`, `APPLIED`, `FAILED`, `PARTIAL` (reserved), `ROLLED_BACK` (future).

Operation statuses during apply: `PENDING` → `RUNNING` → `DONE` / `FAILED` / `SKIPPED`.

Rollback UI is not implemented yet, but logs retain `rollback_data`.

## Path Safety Rules

## TV Series Layer

The TV layer is separate from the movie-oriented `MediaItem` workflow. It adds first-class show grouping tables: `tv_shows`, `tv_seasons`, `tv_episodes`, and `tv_grouping_runs`.

`TvFolderContextBuilder` serializes the scan tree into paths, folders, file kinds, sidecar NFO IDs, artwork hints, sizes, mtimes, and deterministic TV hints. It never sends binary media to AI. `tv_hints.py` extracts season/episode hints from `S01E01`, `1x02`, English season/episode words, Russian `сезон/серия` forms, numeric episode files inside season folders, and release-group junk tokens.

The TV pipeline is:

```text
folder tree -> deterministic hints -> local TV grouping -> TMDB TV match -> Gemini audit -> TV review -> TV dry-run plan
```

Local/cloud AI clients can provide structured grouping/audit responses; when unavailable, deterministic grouping and identity audit keep the workflow inspectable. `tv_grouping_runs` stores input/output JSON, provider, model, status, duration, and errors.

TMDB TV matching uses `/search/tv`, `/tv/{id}`, `/tv/{id}/season/{season_number}`, and `/find/{external_id}`. Russian metadata is requested first with English fallback; artwork prefers `ru,null,en`. Sidecar IDs are preferred over title queries.

TV planning creates a normal `OperationPlan`, but every TV operation has `tv_apply_disabled=true`. `ApplyService` rejects such plans before filesystem writes. Target paths are direct under the selected target root and do not add `TV Shows`.

Before validation and apply:

- Source paths for `MOVE_FILE` must stay inside `scan_session.source_path`.
- Target paths must stay inside `scan_session.target_path`.
- Paths are normalized with `pathlib` (`resolve`) and checked with `relative_to`.
- `DOWNLOAD_FILE` URLs must be HTTPS from `image.tmdb.org` only.
- Escaping roots or `..` traversal is treated as a conflict/security error.

## Bulk Review API

- `POST /scan-sessions/{id}/review/approve-all` — bulk approve by `matched` or `selected` scope.
- `POST /scan-sessions/{id}/review/bulk-decision` — bulk `approved` / `ignored` / `deferred` (no `manual_override`).

Ignored and deferred items are excluded from planning via `list_plannable_by_scan_session`.

## Scan Session Deletion

`DELETE /scan-sessions/{id}` removes the scan session and all related SQLite rows:
- `media_files`
- `media_items` and `tmdb_match_candidates`
- `operation_plans` and `plan_operations`
- session-linked `media_items` and their `tmdb_match_candidates`

`recognition_corrections` are detached (`media_item_id = null`), not deleted. Global `recognition_token_rules` and `processed_media_records` are preserved. Files on disk are never modified or deleted.

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

## Safe Preview and Apply Mode

The session detail page shows that the plan is preview-only until the user explicitly confirms apply. Files change on disk only after **Применить план** with the confirmation checkbox.

Apply is blocked when validation reports conflicts or the plan is not `READY`.

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

## Human Override Flow

Users can correct wrong TMDB matches without touching files on disk:

1. Manual search: `POST /items/{item_id}/tmdb-search` with title/year/media_type (`ru-RU` first, `en-US` fallback).
2. Manual ID lookup: `POST /items/{item_id}/tmdb-lookup` with `tmdb_id`, `imdb_id`, or `tvdb_id`.
3. Candidate select: `POST /items/{item_id}/tmdb-candidates/{candidate_id}/select`.
4. Review decision: `POST /items/{item_id}/review-decision` with `approved`, `ignored`, `deferred`, or `manual_override`.

`MediaItem.review_decision` values:

| Decision | Planning |
|----------|----------|
| `pending` | Included if `MATCHED` and not ignored/deferred |
| `approved` | Included |
| `manual_override` | Included; uses manually loaded TMDB data |
| `ignored` | Excluded |
| `deferred` | Excluded |

Manual overrides upsert `ProcessedMediaRecord` and create `RecognitionCorrection` entries for memory reuse.

## Manual ID Lookup

- **TMDB ID**: direct `/movie/{id}` or `/tv/{id}` with `append_to_response=external_ids,images,translations`.
- **IMDb ID**: TMDB `/find/{imdb_id}?external_source=imdb_id`, then details.
- **TVDB ID**: TMDB `/find/{tvdb_id}?external_source=tvdb_id`, then details.

Lookup creates or updates `TmdbMatchCandidate` rows but does not auto-select unless review-decision or select endpoint is used.

## Cloud Primary / Fallback

`AppSettings` stores primary cloud AI (`cloud_ai_*`) and optional fallback (`cloud_ai_fallback_*`). If fallback key is empty but provider matches primary, the primary key is reused.

`RecognitionService.preflight()` checks local LLM, primary cloud, and fallback cloud. Pipeline is allowed when local + (primary OR fallback) succeed. Warning is returned when only fallback works.

During `resolve_with_gemini`, primary cloud is tried per item; on failure the fallback client is used. Diagnostics are stored in `gemini_*` item fields including which model actually ran.

## Sidecar Metadata Extraction

After parse, `SidecarMetadataService` scans the video folder for NFO and image sidecars. Parsed NFO fields populate `MediaItem.sidecar_*` and `local_poster_path`. Status: `not_found`, `found`, `parse_failed`.

## ID Priority Flow

Before title search, `TMDBService._try_priority_id_lookup` tries IDs in order:

1. `manual_tmdb_id` / `manual_imdb_id` / `manual_tvdb_id`
2. `sidecar_tmdb_id` / `sidecar_imdb_id` / `sidecar_tvdb_id`
3. memory IDs when `reused_from_memory`
4. title/year TMDB search with Cyrillic-first queries

`match_source` records why an item matched (`sidecar_imdb_id`, `tmdb_search`, `manual_override`, etc.).

## Local Poster vs TMDB Match

A local poster from disk may be shown with badge `Локальный постер`, but `Найдено в TMDB` requires `tmdb_id`. UI badges are computed centrally in `frontend/src/badges.ts`.

## Item Badge / Status Consistency

Badges are mutually consistent: an item with `tmdb_id` shows `Найдено в TMDB`; `manual_override` shows `Исправлено вручную`; sidecar ID match shows `Найдено по локальному ID`. Technical AI diagnostics are collapsed under `Технические детали распознавания`.

## Manual Lookup Item Update

`POST /items/{id}/tmdb-lookup` and candidate select update all match fields (`tmdb_id`, external IDs, localized metadata, `review_decision`, memory). Frontend reloads items after select/lookup.
