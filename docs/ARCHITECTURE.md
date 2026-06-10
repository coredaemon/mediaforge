# Architecture

MediaForge is designed as a local-first web application with a Python backend, SQLite database, and future web UI.

## Layers

- **FastAPI API layer** exposes HTTP endpoints and delegates all workflow decisions to services.
- **Service layer** coordinates application use cases such as scanning, parsing, planning, applying, and rollback.
- **Repository layer** owns database reads and writes behind explicit interfaces.
- **SQLite database** stores local application state and materialized operation plans.
- **Scanner** discovers candidate media files without modifying the filesystem.
- **Parser** turns filenames and folder context into structured candidates.
- **AI Analyzer** may help interpret messy names, but it does not define truth.
- **TMDB Client** resolves confirmed matches against the canonical metadata source.
- **Planner** builds dry-run operation plans for preview.
- **Apply Engine** applies only approved, materialized operation plans.
- **Rollback Engine** reverses applied operations using recorded plan data.
- **Web UI** will provide local previews, confirmation flows, and progress visibility.

## Pipeline

```text
DISCOVERED -> PARSED -> MATCHED -> PLANNED -> READY_TO_APPLY -> APPLYING -> COMPLETED
                                                                  \-> FAILED
                                                                  \-> ROLLED_BACK
```

The pipeline is intentionally staged so discovery and planning can be inspected before any filesystem changes are attempted.

## Current Models

- `ScanSession` stores source and target paths, lifecycle status, timestamps, and errors.
- `MediaFile` stores discovered file paths, names, extensions, sizes, classification, and scan errors.
- `MediaItem` stores parsed movie, TV episode, or unknown local candidates.
- `OperationPlan` stores a materialized dry-run plan for a scan session.
- `PlanOperation` stores one planned filesystem or metadata action such as `CREATE_DIR`, `MOVE_FILE`, `WRITE_TEXT_FILE`, or `DOWNLOAD_FILE`.

## Current Scanner Flow

The scanner currently performs discovery only:

1. Load the `ScanSession` from SQLite.
2. Validate that `source_path` exists and is a directory.
3. Mark the session as `DISCOVERING`.
4. Walk the source directory with `os.scandir()`.
5. Classify files as `VIDEO`, `SUBTITLE`, `SIDECAR`, or `OTHER`.
6. Store each discovered file in `MediaFile`.
7. Mark the session as `DISCOVERED`, or `FAILED` for critical errors.

It does not parse titles, call TMDB, call AI providers, build apply plans, move files, delete files, download posters, or generate NFO files.

## Current Parser Flow

The parser is deterministic and local. It works only from already discovered `MediaFile` rows and never touches the filesystem.

1. Load the `ScanSession` from SQLite.
2. Mark the session as `PARSING`.
3. Select discovered `VIDEO` files.
4. Parse filenames using local rules for movie years and TV episode patterns such as `S01E01` and `1x02`.
5. Remove common technical tokens such as `1080p`, `BluRay`, `WEB-DL`, `x264`, and release tags from parsed titles.
6. Create one `MediaItem` candidate per unlinked video file.
7. Link each parsed video `MediaFile` to its `MediaItem`.
8. Mark the session as `PARSED`.

Unknown or low-confidence filenames become `UNKNOWN` items with `NEEDS_REVIEW`. The parser does not call AI or TMDB; those later layers will validate and enrich candidates.

## Current TMDB Matching Flow

TMDB is the canonical metadata source after local parsing creates a candidate. AI is not used in the matching layer.

1. Load parsed `MediaItem` rows for a scan session.
2. Match only `MOVIE` and `TV_EPISODE` items with a parsed title.
3. Search TMDB movies for movies and TMDB TV shows for TV episodes.
4. Store all returned matches as `TmdbMatchCandidate` rows.
5. Score candidates using title similarity, exact title bonus, year bonus, and a small popularity bonus.
6. Automatically select the best candidate when `score >= 0.80`.
7. Mark uncertain candidates as `NEEDS_REVIEW`.
8. Mark items with no candidates as `UNMATCHED`.

Candidates are separate from the selected match. Auto-selected matches update `MediaItem.tmdb_id`, `tmdb_media_type`, `matched_title`, `matched_year`, and `match_confidence`. Re-running matching does not duplicate candidates; old candidates for a rematched item are deleted before new candidates are saved.

The TMDB API key is read only from local environment configuration. The app starts without a key, but matching requests return a clear `TMDB_API_KEY is not configured` error until a local key is provided.

## Dry-run Planning Layer

Planning is separated from apply on purpose. Discovery, parsing, and TMDB matching only prepare candidates. Planning turns confirmed `MATCHED` items into a materialized `OperationPlan` stored in SQLite so the user can inspect future filesystem changes before anything is executed.

The planning layer is dry-run only:

1. Load the `ScanSession` and its `MATCHED` `MediaItem` rows.
2. Resolve each item's linked video `MediaFile`.
3. Build target library paths with the target path builder in `backend/app/utils/target_paths.py`.
4. Sanitize folder and file names for Windows-safe library layout without changing case or non-Latin titles.
5. Create an `OperationPlan` with status `DRAFT`, then mark it `READY` after operations are materialized.
6. Create `PlanOperation` rows for:
   - `CREATE_DIR` for the destination folder;
   - `MOVE_FILE` from the discovered source video to the target library path;
   - `WRITE_TEXT_FILE` for a future `.nfo` file such as `movie.nfo`;
   - `DOWNLOAD_FILE` for future poster/backdrop artwork when the selected TMDB candidate has image paths.
7. Return the plan and operations through the API.

Planning never creates folders, moves files, writes NFO files, or downloads artwork. It only records intended operations in the database. Apply and rollback engines will consume these materialized plans later, but they are not implemented yet.

### Target Path Builder

Movies are planned into:

```text
{target_path}/Movies/{Matched Title} ({Year})/{Matched Title} ({Year}){extension}
```

TV episodes are planned into:

```text
{target_path}/TV Shows/{Matched Title}/Season 01/{Matched Title} S01E01{extension}
```

Episode-level TMDB metadata is not used yet, so episode titles are not part of the planned filename.

Apply, rollback, and frontend workflows are still not implemented.
