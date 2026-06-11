from sqlalchemy.ext.asyncio import AsyncSession

from ..models.app_settings import AppSettings

_SINGLETON_ID = 1

# Fields that hold secrets: empty string or None must never overwrite an existing value.
_SECRET_FIELDS = frozenset({"tmdb_api_key", "ai_api_key", "cloud_ai_api_key"})
_PLACEHOLDER_SECRETS = frozenset({"MediaOrganizer_API_Key", "YOUR_API_KEY", "PASTE_API_KEY_HERE"})


class AppSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self) -> AppSettings:
        settings = await self.session.get(AppSettings, _SINGLETON_ID)
        if settings is None:
            settings = AppSettings(id=_SINGLETON_ID)
            self.session.add(settings)
            await self.session.flush()
            await self.session.refresh(settings)
        return settings

    async def update(self, payload: dict) -> AppSettings:
        settings = await self.get_or_create()
        for field, value in payload.items():
            if not hasattr(settings, field):
                continue
            # For secret fields skip None and empty string — never wipe a saved key.
            if field in _SECRET_FIELDS and not value:
                continue
            if field in _SECRET_FIELDS and isinstance(value, str) and value.strip() in _PLACEHOLDER_SECRETS:
                continue
            if value is None:
                continue
            setattr(settings, field, value)
        await self.session.flush()
        await self.session.refresh(settings)
        return settings
