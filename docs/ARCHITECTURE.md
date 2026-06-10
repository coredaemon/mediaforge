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
- `MediaItem` is reserved for parsed movie and TV candidates.
- `OperationPlan` and `PlanOperation` are reserved for future dry-run/apply/rollback workflows.

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
