import httpx
import pytest

from backend.app.repositories.app_settings_repository import AppSettingsRepository
from backend.app.schemas.settings import AppSettingsUpdate, CloudModelsRequest
from backend.app.services.ai_router import AiChainExecutor
from backend.app.services.openrouter_client import OpenRouterClient
from backend.app.services.settings_service import SettingsService


async def test_openrouter_settings_save_key_and_chains(db_session) -> None:
    result = await SettingsService(db_session).update_settings(
        AppSettingsUpdate(
            openrouter_api_key="or-key",
            openrouter_fast_chain=["free/model-a", "free/model-b"],
            openrouter_smart_chain=["smart/model"],
        )
    )

    assert result.openrouter_configured is True
    assert result.openrouter_fast_chain == ["free/model-a", "free/model-b"]
    assert result.openrouter_smart_chain == ["smart/model"]
    assert not hasattr(result, "openrouter_api_key")


async def test_openrouter_empty_key_does_not_overwrite_saved_key(db_session) -> None:
    repo = AppSettingsRepository(db_session)
    await repo.update({"openrouter_api_key": "saved-openrouter"})
    await db_session.commit()

    await SettingsService(db_session).update_settings(AppSettingsUpdate(openrouter_api_key=""))
    settings = await repo.get_or_create()

    assert settings.openrouter_api_key == "saved-openrouter"


async def test_openrouter_placeholder_key_ignored(db_session) -> None:
    await SettingsService(db_session).update_settings(AppSettingsUpdate(openrouter_api_key="YOUR_API_KEY"))
    settings = await AppSettingsRepository(db_session).get_or_create()

    assert settings.openrouter_api_key is None


async def test_openrouter_model_discovery_parses_metadata(db_session, monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "data": [
                    {
                        "id": "openai/gpt-test:free",
                        "name": "GPT Test",
                        "context_length": 128000,
                        "pricing": {"prompt": "0", "completion": "0"},
                    }
                ]
            }

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            assert url == "https://openrouter.ai/api/v1/models"
            assert headers["Authorization"] == "Bearer or-key"
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await SettingsService(db_session).get_cloud_models(
        CloudModelsRequest(provider="openrouter", api_key="or-key")
    )

    assert result.success is True
    assert result.models[0].id == "openai/gpt-test:free"
    assert result.models[0].context_length == 128000
    assert result.models[0].is_free is True


async def test_openrouter_chat_completion_success(monkeypatch) -> None:
    async def fake_post(url, **kwargs):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        return (
            httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
            ),
            1,
        )

    monkeypatch.setattr("backend.app.services.openrouter_client.post_with_retry", fake_post)
    result = await OpenRouterClient("or-key").chat_json(model="model-a", messages=[{"role": "user", "content": "x"}])

    assert result.content == '{"ok": true}'
    assert result.model == "model-a"


async def test_ai_chain_executor_falls_back_on_invalid_json(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_chat_json(self, *, model, messages):
        from backend.app.services.openrouter_client import OpenRouterChatResult

        calls.append(model)
        content = "not json" if model == "bad" else '{"ok": true}'
        return OpenRouterChatResult(model=model, content=content, attempts=1, duration_ms=1, raw_json={})

    monkeypatch.setattr(OpenRouterClient, "chat_json", fake_chat_json)
    result = await AiChainExecutor(OpenRouterClient("or-key")).run_json(
        models=["bad", "good"],
        messages=[{"role": "user", "content": "x"}],
        quality_gate=lambda data: (data.get("ok") is True, "not ok"),
    )

    assert result.ok is True
    assert result.model == "good"
    assert calls == ["bad", "good"]
    assert len(result.attempted_models) == 2


async def test_ai_chain_executor_returns_human_message_when_all_models_fail(monkeypatch) -> None:
    async def fake_chat_json(self, *, model, messages):
        raise RuntimeError("temporary unavailable for key=secret")

    monkeypatch.setattr(OpenRouterClient, "chat_json", fake_chat_json)
    result = await AiChainExecutor(OpenRouterClient("or-key")).run_json(
        models=["a", "b"],
        messages=[{"role": "user", "content": "x"}],
    )

    assert result.ok is False
    assert result.human_message is not None
    assert "secret" not in (result.technical_error or "")
