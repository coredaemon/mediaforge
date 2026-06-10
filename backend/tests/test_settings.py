from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.repositories.app_settings_repository import AppSettingsRepository
from backend.app.schemas.settings import AppSettingsUpdate
from backend.app.services.settings_service import SettingsService


async def test_get_default_settings_returns_unconfigured_state(db_session: AsyncSession) -> None:
    result = await SettingsService(db_session).get_settings()

    assert result.tmdb_configured is False
    assert result.ai_configured is False
    assert result.setup_completed is False
    assert result.ai_provider is None
    assert result.default_source_path is None


async def test_update_settings_saves_paths_and_flags(db_session: AsyncSession) -> None:
    payload = AppSettingsUpdate(
        default_source_path="/media/inbox",
        default_target_path="/media/library",
        setup_completed=True,
    )
    result = await SettingsService(db_session).update_settings(payload)

    assert result.default_source_path == "/media/inbox"
    assert result.default_target_path == "/media/library"
    assert result.setup_completed is True


async def test_get_settings_does_not_expose_raw_tmdb_key(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update({"tmdb_api_key": "super-secret-key"})
    await db_session.commit()

    result = await SettingsService(db_session).get_settings()

    assert result.tmdb_configured is True
    assert not hasattr(result, "tmdb_api_key")


async def test_update_ai_provider_stores_without_exposing_key(db_session: AsyncSession) -> None:
    payload = AppSettingsUpdate(
        ai_provider="gemini",
        ai_api_key="gemini-secret",
        ai_model="gemini-1.5-flash",
    )
    result = await SettingsService(db_session).update_settings(payload)

    assert result.ai_configured is True
    assert result.ai_provider == "gemini"
    assert result.ai_model == "gemini-1.5-flash"
    assert not hasattr(result, "ai_api_key")


async def test_setup_completed_flag_can_be_set_and_read(db_session: AsyncSession) -> None:
    settings_before = await SettingsService(db_session).get_settings()
    assert settings_before.setup_completed is False

    await SettingsService(db_session).update_settings(AppSettingsUpdate(setup_completed=True))
    settings_after = await SettingsService(db_session).get_settings()

    assert settings_after.setup_completed is True


async def test_test_tmdb_returns_error_when_no_key_configured(db_session: AsyncSession) -> None:
    result = await SettingsService(db_session).test_tmdb()

    assert result.success is False
    assert "не настроен" in result.message.lower()


async def test_test_tmdb_uses_stored_key_and_calls_tmdb(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update({"tmdb_api_key": "fake-key"})
    await db_session.commit()

    with patch(
        "backend.app.services.settings_service.TmdbClient.search_movie",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await SettingsService(db_session).test_tmdb()

    assert result.success is True


async def test_get_ollama_models_returns_error_on_connection_refused(db_session: AsyncSession) -> None:
    result = await SettingsService(db_session).get_ollama_models(endpoint="http://127.0.0.1:19999")

    assert result.success is False
    assert result.models == []
    assert result.message is not None


async def test_get_lmstudio_models_returns_error_on_connection_refused(db_session: AsyncSession) -> None:
    result = await SettingsService(db_session).get_lmstudio_models(endpoint="http://127.0.0.1:19998")

    assert result.success is False
    assert result.models == []
    assert result.message is not None
