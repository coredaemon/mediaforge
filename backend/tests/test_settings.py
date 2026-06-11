import httpx
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.repositories.app_settings_repository import AppSettingsRepository
from backend.app.schemas.settings import AppSettingsUpdate, CloudModelsRequest
from backend.app.services.settings_service import SettingsService
from backend.app.services.recognition_clients import sanitize_error_text


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


# ── Key preservation tests ─────────────────────────────────────────────────


async def test_update_settings_does_not_wipe_tmdb_key_with_empty_string(db_session: AsyncSession) -> None:
    """Sending an empty tmdb_api_key must NOT overwrite an existing saved key."""
    repo = AppSettingsRepository(db_session)
    await repo.update({"tmdb_api_key": "existing-key"})
    await db_session.commit()

    # Simulate what frontend does when user leaves key field blank.
    payload = AppSettingsUpdate(default_source_path="/new/source")
    await SettingsService(db_session).update_settings(payload)

    # Reload and check that the key survived.
    settings = await repo.get_or_create()
    await db_session.refresh(settings)
    assert settings.tmdb_api_key == "existing-key"


async def test_update_settings_does_not_wipe_key_when_empty_string_explicitly_passed(
    db_session: AsyncSession,
) -> None:
    """Repo.update called with empty string for a secret field must skip the update."""
    repo = AppSettingsRepository(db_session)
    await repo.update({"tmdb_api_key": "saved-key"})
    await db_session.commit()

    await repo.update({"tmdb_api_key": ""})
    await db_session.commit()

    settings = await repo.get_or_create()
    await db_session.refresh(settings)
    assert settings.tmdb_api_key == "saved-key"


async def test_update_settings_replaces_tmdb_key_when_non_empty(db_session: AsyncSession) -> None:
    """A non-empty tmdb_api_key in the update payload must replace the stored key."""
    repo = AppSettingsRepository(db_session)
    await repo.update({"tmdb_api_key": "old-key"})
    await db_session.commit()

    await repo.update({"tmdb_api_key": "new-key"})
    await db_session.commit()

    settings = await repo.get_or_create()
    await db_session.refresh(settings)
    assert settings.tmdb_api_key == "new-key"


async def test_placeholder_cloud_key_is_not_saved(db_session: AsyncSession) -> None:
    repo = AppSettingsRepository(db_session)

    await repo.update({"cloud_ai_api_key": "MediaOrganizer_API_Key"})
    await db_session.commit()
    settings = await repo.get_or_create()

    assert settings.cloud_ai_api_key is None


async def test_empty_cloud_key_does_not_overwrite_saved_key(db_session: AsyncSession) -> None:
    repo = AppSettingsRepository(db_session)
    await repo.update({"cloud_ai_api_key": "saved-cloud-key"})
    await db_session.commit()

    await repo.update({"cloud_ai_api_key": ""})
    await db_session.commit()
    settings = await repo.get_or_create()

    assert settings.cloud_ai_api_key == "saved-cloud-key"


async def test_get_settings_does_not_expose_cloud_key(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update(
        {"cloud_ai_provider": "gemini", "cloud_ai_api_key": "saved-cloud-key"}
    )
    await db_session.commit()

    result = await SettingsService(db_session).get_settings()

    assert result.cloud_ai_configured is True
    assert not hasattr(result, "cloud_ai_api_key")


async def test_cloud_model_discovery_gemini_success(db_session: AsyncSession, monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"models": [{"name": "models/gemini-test", "displayName": "Gemini Test", "supportedGenerationMethods": ["generateContent"]}]}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    result = await SettingsService(db_session).get_cloud_models(
        payload=CloudModelsRequest(provider="gemini", api_key="real-key")
    )

    assert result.success is True
    assert result.models[0].id == "gemini-test"


async def test_cloud_model_discovery_openai_invalid_key(db_session: AsyncSession, monkeypatch) -> None:
    class FakeResponse:
        status_code = 401

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await SettingsService(db_session).get_cloud_models(payload=CloudModelsRequest(provider="openai", api_key="bad-key"))

    assert result.success is False
    assert "rejected" in (result.message or "")


def test_sanitize_error_text_redacts_key_query_param() -> None:
    raw = "Client error '400 Bad Request' for url 'https://example.test/path?key=MediaOrganizer_API_Key&x=1'"

    sanitized = sanitize_error_text(raw)

    assert "MediaOrganizer_API_Key" not in sanitized
    assert "key=[redacted]" in sanitized


# ── TMDB test endpoint error message tests ─────────────────────────────────


async def test_test_tmdb_returns_auth_error_message_on_401(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update({"tmdb_api_key": "bad-key"})
    await db_session.commit()

    mock_response = httpx.Response(401, request=httpx.Request("GET", "https://api.themoviedb.org/"))
    with patch(
        "backend.app.services.settings_service.TmdbClient.search_movie",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError("401", request=mock_response.request, response=mock_response),
    ):
        result = await SettingsService(db_session).test_tmdb()

    assert result.success is False
    assert "ключ" in result.message.lower() or "отклонил" in result.message.lower()


async def test_test_tmdb_returns_network_error_message_on_connect_error(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update({"tmdb_api_key": "any-key"})
    await db_session.commit()

    with patch(
        "backend.app.services.settings_service.TmdbClient.search_movie",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        result = await SettingsService(db_session).test_tmdb()

    assert result.success is False
    assert "подключиться" in result.message.lower() or "интернет" in result.message.lower()


async def test_test_tmdb_returns_timeout_message(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update({"tmdb_api_key": "any-key"})
    await db_session.commit()

    with patch(
        "backend.app.services.settings_service.TmdbClient.search_movie",
        new_callable=AsyncMock,
        side_effect=httpx.ReadTimeout("timed out"),
    ):
        result = await SettingsService(db_session).test_tmdb()

    assert result.success is False
    assert "вовремя" in result.message.lower() or "timeout" in result.message.lower()
