# Security

This repository is public. Treat every committed file as visible to everyone.

## Repository Rules

- Real API keys, tokens, and provider credentials are forbidden in commits.
- Use only `.env.example` for placeholder environment values.
- `.env` and local environment variants must stay in `.gitignore`.
- Local SQLite databases must not be committed.
- Logs and caches must not be committed.
- User-specific paths and media files must not be committed.

## Local Secrets

Real TMDB, Gemini, OpenAI, DeepSeek, or other provider keys belong only in:
- the local SQLite database `mediaforge.local.sqlite3` (via the Settings UI), or
- a local `.env` file.

Keep placeholder values empty in committed `.env.example` files.

## API Key Handling

- Keys entered through the Settings UI are stored in `AppSettings` in `mediaforge.local.sqlite3`.
- `GET /settings` returns only boolean flags (`tmdb_configured`, `ai_configured`) — never raw key values.
- `PUT /settings` accepts keys for saving but does not echo them back in the response.
- The env-based `TMDB_API_KEY` remains as a fallback; `AppSettings.tmdb_api_key` takes precedence when set.
- **Write-only principle:** once a key is saved, the UI can only replace it (by entering a new non-empty value) or test it. The raw value is never returned to the browser.
- **Empty field does not wipe secrets:** sending an empty or null `tmdb_api_key` / `ai_api_key` in `PUT /settings` is a no-op — the stored key is preserved. This prevents accidental deletion when the user saves other settings without re-entering keys.
- **Replacement:** a non-empty key string in `PUT /settings` replaces the stored key.
- **`configured` flags:** the UI uses `tmdb_configured: true/false` to show "key saved" status without exposing the key itself.

## Filesystem Browser

- `GET /filesystem/roots` and `GET /filesystem/browse` are read-only endpoints.
- They list directories only — no file content is read.
- No create, move, copy, or delete operations are exposed.
- The browser does not execute shell commands.

## Safe Preview Mode

- Discovery, parsing, TMDB matching, and planning never modify the filesystem.
- Planning creates only database records (`OperationPlan`, `PlanOperation`).
- Apply and rollback are not implemented and cannot be triggered from the UI.
