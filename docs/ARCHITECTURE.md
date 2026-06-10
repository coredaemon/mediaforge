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
