from sqlalchemy.ext.asyncio import AsyncSession

from ..models.app_settings import AppSettings

_SINGLETON_ID = 1


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
            if hasattr(settings, field) and value is not None:
                setattr(settings, field, value)
        await self.session.flush()
        await self.session.refresh(settings)
        return settings
