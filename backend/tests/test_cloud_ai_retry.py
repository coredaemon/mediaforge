import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.repositories.app_settings_repository import AppSettingsRepository
from backend.app.schemas.recognition import LlmPreflightCheck
from backend.app.services.recognition_clients import GeminiTitleNormalizer
from backend.app.services.recognition_service import RecognitionService
from backend.app.services.settings_service import SettingsService
from backend.app.utils.ai_errors import humanize_ai_error, sanitize_error_text
from backend.app.utils.ai_retry import execute_with_retry, post_with_retry
from backend.tests.fakes import FakeTitleNormalizer


def _http_error(status: int) -> httpx.HTTPStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.com"))
    return httpx.HTTPStatusError(f"{status}", request=response.request, response=response)


async def test_cloud_test_retries_on_503_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def fake_client_post(self, url, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _http_error(503)
        response = httpx.Response(200, request=httpx.Request("POST", url))
        response._content = b'{"candidates":[{"content":{"parts":[{"text":"{\\"ok\\":true,\\"provider\\":\\"gemini\\",\\"test\\":\\"mediaforge-preflight\\"}"}]}}]}'
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_client_post)

    result = await GeminiTitleNormalizer("test-key", "gemini-2.0-flash").preflight("gemini")
    assert result.ok
    assert calls == 2
    assert result.attempts == 2


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_post_with_retry_on_status_codes(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    calls = 0

    async def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _http_error(status)
        response = httpx.Response(200, request=httpx.Request("POST", "https://example.com"))
        response._content = b"{}"
        return response

    async def fake_client_post(self, url, **kwargs):
        return await fake_post(url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_client_post)

    response, attempts = await post_with_retry("https://example.com", timeout=1.0)
    assert response.status_code == 200
    assert attempts == 3


@pytest.mark.parametrize("status", [401, 403, 404])
async def test_post_with_retry_does_not_retry_auth_or_not_found(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    calls = 0

    async def fake_client_post(self, url, **kwargs):
        nonlocal calls
        calls += 1
        raise _http_error(status)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_client_post)
    with pytest.raises(Exception):
        await post_with_retry("https://example.com", timeout=1.0)
    assert calls == 1


async def test_preflight_ok_when_primary_503_fallback_ok(db_session: AsyncSession) -> None:
    primary = FakeTitleNormalizer()
    fallback = FakeTitleNormalizer()

    async def primary_preflight(expected_provider: str) -> LlmPreflightCheck:
        return LlmPreflightCheck(
            ok=False,
            provider="gemini",
            model="primary",
            duration_ms=12,
            error="503 Service Unavailable",
            error_type="temporary_unavailable",
            human_message=humanize_ai_error("503", status_code=503, error_type="temporary_unavailable"),
            retryable=True,
            attempts=3,
        )

    primary.preflight = primary_preflight  # type: ignore[method-assign]

    service = RecognitionService(db_session, gemini_client=primary)

    async def patched_get(self, use_gemini: bool, use_fallback: bool = False):
        if not use_gemini:
            return FakeTitleNormalizer()
        if use_fallback:
            return fallback
        return primary

    original_get = RecognitionService._get_client
    RecognitionService._get_client = patched_get  # type: ignore[method-assign]
    try:
        result = await service.preflight()
    finally:
        RecognitionService._get_client = original_get  # type: ignore[method-assign]

    assert result.ok
    assert result.cloud.retryable
    assert "временно недоступна" in (result.warning or "").lower()


async def test_preflight_warns_when_openrouter_fast_fails_but_smart_ok(db_session: AsyncSession) -> None:
    fast = FakeTitleNormalizer()
    smart = FakeTitleNormalizer()

    async def fast_preflight(expected_provider: str) -> LlmPreflightCheck:
        return LlmPreflightCheck(
            ok=False,
            provider="openrouter",
            model="free/limited",
            error="429 Too Many Requests",
            error_type="chain_failed",
            human_message="Fast chain failed",
            retryable=True,
            attempts=1,
            attempted_models=[
                {
                    "model": "free/limited",
                    "ok": False,
                    "duration_ms": 3,
                    "http_status": 429,
                    "error_type": "rate_limited",
                }
            ],
        )

    fast.preflight = fast_preflight  # type: ignore[method-assign]

    service = RecognitionService(db_session)

    async def patched_get(self, use_gemini: bool, use_fallback: bool = False):
        if use_gemini:
            return None if use_fallback else smart
        return fast

    original_get = RecognitionService._get_client
    RecognitionService._get_client = patched_get  # type: ignore[method-assign]
    try:
        result = await service.preflight()
    finally:
        RecognitionService._get_client = original_get  # type: ignore[method-assign]

    assert result.ok
    assert result.warning
    assert result.local.attempted_models[0]["model"] == "free/limited"


async def test_preflight_blocks_when_openrouter_fast_auth_fails(db_session: AsyncSession) -> None:
    fast = FakeTitleNormalizer()
    smart = FakeTitleNormalizer()

    async def fast_preflight(expected_provider: str) -> LlmPreflightCheck:
        return LlmPreflightCheck(
            ok=False,
            provider="openrouter",
            model="free/auth",
            error="401 Unauthorized",
            error_type="auth_error",
            human_message="Auth failed",
            attempts=1,
        )

    fast.preflight = fast_preflight  # type: ignore[method-assign]

    service = RecognitionService(db_session)

    async def patched_get(self, use_gemini: bool, use_fallback: bool = False):
        if use_gemini:
            return None if use_fallback else smart
        return fast

    original_get = RecognitionService._get_client
    RecognitionService._get_client = patched_get  # type: ignore[method-assign]
    try:
        result = await service.preflight()
    finally:
        RecognitionService._get_client = original_get  # type: ignore[method-assign]

    assert not result.ok
    assert result.message


async def test_preflight_fails_when_both_cloud_503(db_session: AsyncSession) -> None:
    async def fail_preflight(expected_provider: str) -> LlmPreflightCheck:
        return LlmPreflightCheck(
            ok=False,
            provider="gemini",
            model="m",
            duration_ms=10,
            error="503 Service Unavailable",
            error_type="temporary_unavailable",
            human_message=humanize_ai_error("503", status_code=503, error_type="temporary_unavailable"),
            retryable=True,
            attempts=3,
        )

    primary = FakeTitleNormalizer()
    fallback = FakeTitleNormalizer()
    primary.preflight = fail_preflight  # type: ignore[method-assign]
    fallback.preflight = fail_preflight  # type: ignore[method-assign]

    service = RecognitionService(db_session, gemini_client=primary)

    async def patched_get(self, use_gemini: bool, use_fallback: bool = False):
        if not use_gemini:
            return FakeTitleNormalizer()
        if use_fallback:
            return fallback
        return primary

    original_get = RecognitionService._get_client
    RecognitionService._get_client = patched_get  # type: ignore[method-assign]
    try:
        result = await service.preflight()
    finally:
        RecognitionService._get_client = original_get  # type: ignore[method-assign]

    assert not result.ok
    assert "облачные модели временно недоступны" in (result.message or "").lower()


def test_humanize_503_message() -> None:
    msg = humanize_ai_error("503 Service Unavailable", status_code=503, error_type="temporary_unavailable")
    assert "временно недоступна" in msg.lower()


def test_sanitize_error_never_leaks_key() -> None:
    raw = "Server error for url https://api.example.com?key=super-secret-key-12345"
    sanitized = sanitize_error_text(raw)
    assert "super-secret-key" not in sanitized
    assert "[redacted]" in sanitized


async def test_settings_primary_test_returns_preflight_shape(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.schemas.settings import CloudAiTestRequest

    await AppSettingsRepository(db_session).update(
        {
            "cloud_ai_provider": "gemini",
            "cloud_ai_api_key": "primary-key",
            "cloud_ai_model": "gemini-2.0-flash",
            "cloud_ai_fallback_provider": "gemini",
            "cloud_ai_fallback_api_key": "fallback-key",
            "cloud_ai_fallback_model": "gemini-1.5-flash",
        }
    )
    await db_session.commit()

    async def fake_preflight(self, expected_provider: str) -> LlmPreflightCheck:
        return LlmPreflightCheck(
            ok=False,
            provider="gemini",
            model="gemini-2.0-flash",
            error="503 Service Unavailable",
            error_type="temporary_unavailable",
            human_message=humanize_ai_error("503", status_code=503, error_type="temporary_unavailable"),
            retryable=True,
            attempts=3,
        )

    from backend.app.services.recognition_clients import GeminiTitleNormalizer

    monkeypatch.setattr(GeminiTitleNormalizer, "preflight", fake_preflight, raising=False)
    result = await SettingsService(db_session).test_cloud_ai(
        CloudAiTestRequest(provider="gemini", model="gemini-2.0-flash")
    )

    assert not result.ok
    assert result.human_message is not None
    assert "primary-key" not in str(result.model_dump())


async def test_empty_cloud_key_does_not_overwrite_saved_key(db_session: AsyncSession) -> None:
    from backend.app.schemas.settings import AppSettingsUpdate

    await SettingsService(db_session).update_settings(
        AppSettingsUpdate(cloud_ai_api_key="saved-primary", cloud_ai_provider="gemini", cloud_ai_model="m1")
    )
    await SettingsService(db_session).update_settings(AppSettingsUpdate(cloud_ai_api_key=""))
    settings = await AppSettingsRepository(db_session).get_or_create()
    assert settings.cloud_ai_api_key == "saved-primary"


async def test_get_settings_does_not_expose_keys(db_session: AsyncSession) -> None:
    await AppSettingsRepository(db_session).update(
        {
            "cloud_ai_api_key": "secret-primary",
            "cloud_ai_fallback_api_key": "secret-fallback",
        }
    )
    await db_session.commit()
    result = await SettingsService(db_session).get_settings()
    dumped = result.model_dump()
    assert "secret-primary" not in str(dumped)
    assert "secret-fallback" not in str(dumped)
