# AI Instructions

MediaForge is a public, local-first project. AI agents working in this repository must follow these rules:

- Do not put business logic in FastAPI routers.
- Use the service layer for application workflows.
- Use the repository pattern for database access.
- Use `pathlib` for filesystem paths.
- Do not build paths by concatenating strings.
- Do not commit secrets, API keys, tokens, local configuration, databases, caches, logs, temporary files, absolute user paths, or media files.
- Do not leave `pass` or TODO markers in code that is considered complete.
- Write tests first for core logic.
- Dry-run code must never change the filesystem.
- Do not implement apply or rollback without a materialized operation plan.
- AI is not a source of truth. It may only help prepare candidate interpretations for messy names.
- TMDB is the canonical metadata source after a match is confirmed.
