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

Real TMDB, Gemini, OpenAI, DeepSeek, or other provider keys belong only in a local `.env` file or a local secret manager. Keep placeholder values empty in committed examples.
