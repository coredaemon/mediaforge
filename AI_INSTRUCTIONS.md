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

## Agent workflow

The coding agent is responsible for routine project maintenance commands.

For every completed task, the agent must:

- inspect git status before making changes;
- keep changes focused and minimal;
- run relevant tests;
- inspect git diff before committing;
- ensure no secrets, .env files, local databases, logs, caches, media files, or user-specific paths are committed;
- create a meaningful commit;
- push to origin/main unless explicitly told not to;
- report commit hash, test results, changed files, and push status.

The agent must not ask the user to run routine git, test, formatting, or smoke-test commands if the agent can run them directly.
