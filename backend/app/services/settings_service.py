import json

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.app_settings_repository import AppSettingsRepository
from ..schemas.settings import (
    AppSettingsRead,
    AppSettingsUpdate,
    CloudAiTestRequest,
    CloudModelRead,
    CloudModelsRequest,
    CloudModelsResult,
    LocalModelsResult,
    TestConnectionResult,
)
from ..schemas.recognition import LlmPreflightCheck
from .recognition_clients import GeminiTitleNormalizer, OpenAICompatibleTitleNormalizer, sanitize_error_text
from .ai_router import AiChainExecutor, dump_model_chain, parse_model_chain
from .openrouter_client import OPENROUTER_BASE_URL, OpenRouterClient
from .tmdb_client import TmdbClient

_TMDB_TEST_TIMEOUT = 8.0
_LOCAL_AI_TIMEOUT = 5.0
_CLOUD_AI_TIMEOUT = 20.0


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AppSettingsRepository(session)

    async def get_settings(self) -> AppSettingsRead:
        s = await self.repo.get_or_create()
        await self.session.commit()
        return AppSettingsRead(
            tmdb_configured=bool(s.tmdb_api_key),
            ai_configured=bool(s.ai_provider and s.ai_provider != "none"),
            ai_provider=s.ai_provider,
            ai_base_url=s.ai_base_url,
            ai_model=s.ai_model,
            cloud_ai_configured=bool(
                s.cloud_ai_provider and s.cloud_ai_provider != "none" and _usable_secret(s.cloud_ai_api_key)
            ),
            cloud_primary_configured=bool(
                s.cloud_ai_provider and s.cloud_ai_provider != "none" and _usable_secret(s.cloud_ai_api_key)
            ),
            cloud_fallback_configured=_cloud_fallback_configured(s),
            cloud_ai_provider=s.cloud_ai_provider,
            cloud_ai_base_url=s.cloud_ai_base_url,
            cloud_ai_model=s.cloud_ai_model,
            cloud_ai_fallback_provider=s.cloud_ai_fallback_provider,
            cloud_ai_fallback_model=s.cloud_ai_fallback_model,
            openrouter_configured=bool(_usable_secret(s.openrouter_api_key)),
            openrouter_base_url=s.openrouter_base_url or OPENROUTER_BASE_URL,
            openrouter_fast_chain=parse_model_chain(s.openrouter_fast_chain),
            openrouter_smart_chain=parse_model_chain(s.openrouter_smart_chain),
            recognition_ai_enabled=s.recognition_ai_enabled,
            default_source_path=s.default_source_path,
            default_target_path=s.default_target_path,
            setup_completed=s.setup_completed,
            updated_at=s.updated_at,
        )

    async def update_settings(self, payload: AppSettingsUpdate) -> AppSettingsRead:
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        if payload.setup_completed is not None:
            data["setup_completed"] = payload.setup_completed
        if payload.ai_provider is not None:
            data["ai_provider"] = payload.ai_provider
        if payload.cloud_ai_provider is not None:
            data["cloud_ai_provider"] = payload.cloud_ai_provider
        if payload.cloud_ai_api_key is not None and not _usable_secret(payload.cloud_ai_api_key):
            data.pop("cloud_ai_api_key", None)
        if payload.cloud_ai_fallback_provider is not None:
            data["cloud_ai_fallback_provider"] = payload.cloud_ai_fallback_provider
        if payload.cloud_ai_fallback_api_key is not None and not _usable_secret(payload.cloud_ai_fallback_api_key):
            data.pop("cloud_ai_fallback_api_key", None)
        if payload.openrouter_api_key is not None and not _usable_secret(payload.openrouter_api_key):
            data.pop("openrouter_api_key", None)
        if payload.openrouter_fast_chain is not None:
            data["openrouter_fast_chain"] = dump_model_chain(payload.openrouter_fast_chain)
        if payload.openrouter_smart_chain is not None:
            data["openrouter_smart_chain"] = dump_model_chain(payload.openrouter_smart_chain)
        if payload.recognition_ai_enabled is not None:
            data["recognition_ai_enabled"] = payload.recognition_ai_enabled
        await self.repo.update(data)
        await self.session.commit()
        return await self.get_settings()

    async def test_tmdb(self, api_key: str | None = None) -> TestConnectionResult:
        s = await self.repo.get_or_create()
        key = api_key or s.tmdb_api_key
        if not key:
            return TestConnectionResult(success=False, message="TMDB-ключ не настроен. Введите API ключ с themoviedb.org.")
        client = TmdbClient(key, timeout_seconds=_TMDB_TEST_TIMEOUT)
        try:
            results = await client.search_movie("The Matrix", year=1999)
            if results:
                return TestConnectionResult(success=True, message="TMDB подключён успешно")
            return TestConnectionResult(success=True, message="TMDB подключён (тестовый запрос вернул пустой результат)")
        except httpx.TimeoutException:
            return TestConnectionResult(
                success=False,
                message="TMDB не ответил вовремя. Проверьте интернет-соединение.",
            )
        except httpx.ConnectError:
            return TestConnectionResult(
                success=False,
                message="Не удалось подключиться к TMDB. Проверьте интернет.",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                return TestConnectionResult(
                    success=False,
                    message="TMDB отклонил ключ. Проверьте API key на themoviedb.org.",
                )
            return TestConnectionResult(
                success=False,
                message=f"TMDB вернул ошибку {exc.response.status_code}.",
            )
        except Exception as exc:
            return TestConnectionResult(success=False, message=f"Ошибка TMDB: {exc}")

    async def test_ai(self) -> TestConnectionResult:
        s = await self.repo.get_or_create()
        provider = s.ai_provider or "none"
        if provider == "none" or not provider:
            return TestConnectionResult(success=True, message="AI-помощник отключён")
        if provider == "gemini":
            if not s.ai_api_key:
                return TestConnectionResult(success=False, message="Gemini API ключ не настроен")
            return await _test_gemini(s.ai_api_key)
        if provider in {"ollama", "lmstudio"}:
            base = s.ai_base_url or (_default_endpoint(provider))
            return await _test_openai_compatible(base)
        if provider == "custom":
            if not s.ai_base_url:
                return TestConnectionResult(success=False, message="Base URL не задан")
            return await _test_openai_compatible(s.ai_base_url, api_key=s.ai_api_key)
        return TestConnectionResult(success=False, message=f"Неизвестный провайдер: {provider}")

    async def get_ollama_models(self, endpoint: str = "http://127.0.0.1:11434") -> LocalModelsResult:
        try:
            async with httpx.AsyncClient(timeout=_LOCAL_AI_TIMEOUT) as client:
                resp = await client.get(f"{endpoint.rstrip('/')}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return LocalModelsResult(success=True, models=models)
        except httpx.ConnectError:
            return LocalModelsResult(success=False, models=[], message=f"Ollama не отвечает по адресу {endpoint}")
        except Exception as exc:
            return LocalModelsResult(success=False, models=[], message=str(exc))

    async def get_lmstudio_models(self, endpoint: str = "http://127.0.0.1:1234") -> LocalModelsResult:
        try:
            async with httpx.AsyncClient(timeout=_LOCAL_AI_TIMEOUT) as client:
                resp = await client.get(f"{endpoint.rstrip('/')}/v1/models")
                resp.raise_for_status()
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
                return LocalModelsResult(success=True, models=models)
        except httpx.ConnectError:
            return LocalModelsResult(success=False, models=[], message=f"LM Studio не отвечает по адресу {endpoint}")
        except Exception as exc:
            return LocalModelsResult(success=False, models=[], message=str(exc))

    async def get_cloud_models(self, payload: CloudModelsRequest) -> CloudModelsResult:
        settings = await self.repo.get_or_create()
        provider = payload.provider
        if provider == "gemini":
            key = payload.api_key if _usable_secret(payload.api_key) else settings.cloud_ai_api_key
            if not _usable_secret(key) and settings.cloud_ai_fallback_provider == "gemini":
                key = settings.cloud_ai_fallback_api_key or settings.cloud_ai_api_key
            if not _usable_secret(key):
                return CloudModelsResult(success=False, models=[], message="API-ключ Gemini не настроен.")
            return await _get_gemini_models(key)
        if provider == "openrouter":
            key = payload.api_key if _usable_secret(payload.api_key) else settings.openrouter_api_key
            if not _usable_secret(key):
                return CloudModelsResult(success=False, models=[], message="API-ключ OpenRouter не настроен.")
            base_url = payload.base_url or settings.openrouter_base_url or OPENROUTER_BASE_URL
            try:
                models = await OpenRouterClient(key, base_url).list_models()
                settings.openrouter_last_models_cache = json.dumps(
                    [model.model_dump() for model in models],
                    ensure_ascii=False,
                )
                await self.session.commit()
                return CloudModelsResult(success=True, models=models)
            except Exception as exc:
                return CloudModelsResult(success=False, models=[], message=sanitize_error_text(str(exc)))
        if provider in {"openai", "custom"}:
            key = payload.api_key if _usable_secret(payload.api_key) else settings.cloud_ai_api_key
            if not _usable_secret(key) and settings.cloud_ai_fallback_provider == provider:
                key = settings.cloud_ai_fallback_api_key or settings.cloud_ai_api_key
            base_url = payload.base_url or settings.cloud_ai_base_url or "https://api.openai.com"
            if provider == "openai" and not _usable_secret(key):
                return CloudModelsResult(success=False, models=[], message="API-ключ OpenAI не настроен.")
            return await _get_openai_models(base_url, key)
        return CloudModelsResult(success=False, models=[], message=f"Облачный провайдер не поддерживается: {provider}")

    async def test_cloud_ai(self, payload: CloudAiTestRequest):
        settings = await self.repo.get_or_create()
        provider = payload.provider
        model = payload.model or settings.cloud_ai_model
        key = payload.api_key if _usable_secret(payload.api_key) else settings.cloud_ai_api_key
        if not _usable_secret(key) and provider == settings.cloud_ai_fallback_provider:
            key = settings.cloud_ai_fallback_api_key or settings.cloud_ai_api_key
        if payload.model and payload.model == settings.cloud_ai_fallback_model:
            model = settings.cloud_ai_fallback_model
        base_url = payload.base_url or settings.cloud_ai_base_url
        if provider == "gemini":
            if not _usable_secret(key):
                return LlmPreflightCheck(
                    ok=False,
                    provider="gemini",
                    model=model,
                    error="API-ключ Gemini не настроен.",
                    error_type="not_configured",
                )
            if not model:
                return LlmPreflightCheck(
                    ok=False,
                    provider="gemini",
                    error="Модель Gemini не выбрана.",
                    error_type="not_configured",
                )
            return await GeminiTitleNormalizer(key, model).preflight("gemini")
        if provider == "openrouter":
            key = payload.api_key if _usable_secret(payload.api_key) else settings.openrouter_api_key
            base_url = payload.base_url or settings.openrouter_base_url or OPENROUTER_BASE_URL
            chain = [model for model in (payload.models or []) if model.strip()]
            if not chain and payload.stage == "fast":
                chain = parse_model_chain(settings.openrouter_fast_chain)
            if not chain and payload.stage == "smart":
                chain = parse_model_chain(settings.openrouter_smart_chain)
            if not _usable_secret(key):
                return LlmPreflightCheck(
                    ok=False,
                    provider="openrouter",
                    model=model,
                    endpoint=base_url,
                    error="API-ключ OpenRouter не настроен.",
                    error_type="not_configured",
                )
            if chain:
                result = await AiChainExecutor(OpenRouterClient(key, base_url)).run_json(
                    models=chain,
                    messages=[{"role": "user", "content": _preflight_prompt()}],
                    quality_gate=lambda data: (
                        data.get("ok") is True and data.get("test") == "mediaforge-preflight",
                        "Preflight JSON did not match expected fields.",
                    ),
                )
                return LlmPreflightCheck(
                    ok=result.ok,
                    provider="openrouter",
                    model=result.model,
                    endpoint=base_url,
                    duration_ms=result.duration_ms,
                    response_valid_json=result.ok,
                    message="Цепочка OpenRouter ответила успешно." if result.ok else None,
                    error=result.technical_error,
                    error_type=None if result.ok else "chain_failed",
                    human_message=(
                        _chain_success_message(payload.stage or "chain", result.model, len(result.attempted_models))
                        if result.ok
                        else "Все модели цепочки недоступны. Проверьте список попыток и выберите другие модели."
                    ),
                    attempts=max(1, len(result.attempted_models)),
                    attempted_models=[
                        {
                            "model": attempt.model,
                            "ok": attempt.ok,
                            "duration_ms": attempt.duration_ms,
                            "attempts": attempt.attempts,
                            "http_status": attempt.http_status,
                            "error_type": attempt.error_type,
                            "error": attempt.error,
                            "human_message": attempt.human_message,
                            "response_valid_json": attempt.response_valid_json,
                        }
                        for attempt in result.attempted_models
                    ],
                    retryable=not result.ok,
                )
            if not model:
                return LlmPreflightCheck(
                    ok=False,
                    provider="openrouter",
                    endpoint=base_url,
                    error="Модель OpenRouter не выбрана.",
                    error_type="not_configured",
                )
            return await OpenAICompatibleTitleNormalizer(base_url, model, key, provider_name="openrouter").preflight("local")
        if provider in {"openai", "custom"}:
            if provider == "openai" and not _usable_secret(key):
                return LlmPreflightCheck(
                    ok=False,
                    provider="openai",
                    model=model,
                    error="API-ключ OpenAI не настроен.",
                    error_type="not_configured",
                )
            if not model:
                return LlmPreflightCheck(
                    ok=False,
                    provider=provider,
                    error="Облачная AI-модель не выбрана.",
                    error_type="not_configured",
                )
            return await OpenAICompatibleTitleNormalizer(base_url or "https://api.openai.com", model, key).preflight("local")
        return LlmPreflightCheck(
            ok=False,
            provider=provider,
            error=f"Облачный провайдер не поддерживается: {provider}",
            error_type="unsupported_provider",
        )


def _default_endpoint(provider: str) -> str:
    return "http://127.0.0.1:11434" if provider == "ollama" else "http://127.0.0.1:1234"


async def _test_gemini(api_key: str) -> TestConnectionResult:
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        async with httpx.AsyncClient(timeout=_TMDB_TEST_TIMEOUT) as client:
            # Pass the key as a param so httpx encodes it, rather than splicing an
            # unescaped secret straight into the URL string.
            resp = await client.get(url, params={"key": api_key})
            if resp.status_code == 200:
                return TestConnectionResult(success=True, message="Gemini подключён успешно")
            return TestConnectionResult(success=False, message=f"Gemini вернул статус {resp.status_code}")
    except Exception as exc:
        return TestConnectionResult(success=False, message=f"Ошибка Gemini: {exc}")


async def _test_openai_compatible(base_url: str, api_key: str | None = None) -> TestConnectionResult:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=_LOCAL_AI_TIMEOUT) as client:
            resp = await client.get(_openai_compatible_url(base_url, "models"), headers=headers)
            if resp.status_code == 200:
                return TestConnectionResult(success=True, message="AI-сервис подключён успешно")
            return TestConnectionResult(success=False, message=f"AI-сервис вернул статус {resp.status_code}")
    except httpx.ConnectError:
        return TestConnectionResult(success=False, message=f"AI-сервис не отвечает по адресу {base_url}")
    except Exception as exc:
        return TestConnectionResult(success=False, message=str(exc))


async def _get_gemini_models(api_key: str) -> CloudModelsResult:
    try:
        async with httpx.AsyncClient(timeout=_CLOUD_AI_TIMEOUT) as client:
            response = await client.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": api_key})
            if response.status_code in {400, 401, 403}:
                return CloudModelsResult(success=False, models=[], message="Gemini API key rejected. Check key and permissions.")
            response.raise_for_status()
            models = []
            for model in response.json().get("models", []):
                methods = model.get("supportedGenerationMethods") or []
                name = str(model.get("name", "")).removeprefix("models/")
                if "generateContent" not in methods or not name:
                    continue
                models.append(
                    CloudModelRead(
                        id=name,
                        label=name,
                        display_name=model.get("displayName"),
                        description=model.get("description"),
                        supported_generation_methods=methods,
                    )
                )
            return CloudModelsResult(success=True, models=models)
    except httpx.ConnectError:
        return CloudModelsResult(success=False, models=[], message="Could not connect to Gemini models API.")
    except Exception as exc:
        return CloudModelsResult(success=False, models=[], message=sanitize_error_text(str(exc)))


async def _get_openai_models(base_url: str, api_key: str | None) -> CloudModelsResult:
    headers = {"Authorization": f"Bearer {api_key}"} if _usable_secret(api_key) else {}
    try:
        async with httpx.AsyncClient(timeout=_CLOUD_AI_TIMEOUT) as client:
            response = await client.get(_openai_compatible_url(base_url, "models"), headers=headers)
            if response.status_code in {400, 401, 403}:
                return CloudModelsResult(success=False, models=[], message="OpenAI API key rejected. Check key and permissions.")
            response.raise_for_status()
            models = [
                CloudModelRead(id=item["id"], label=item["id"])
                for item in response.json().get("data", [])
                if isinstance(item, dict) and item.get("id")
            ]
            return CloudModelsResult(success=True, models=models)
    except httpx.ConnectError:
        return CloudModelsResult(success=False, models=[], message=f"Could not connect to cloud AI endpoint {base_url}.")
    except Exception as exc:
        return CloudModelsResult(success=False, models=[], message=sanitize_error_text(str(exc)))


def _cloud_fallback_configured(settings) -> bool:
    provider = settings.cloud_ai_fallback_provider
    if not provider or provider == "none":
        return False
    key = settings.cloud_ai_fallback_api_key
    if _usable_secret(key):
        return bool(settings.cloud_ai_fallback_model)
    if provider == settings.cloud_ai_provider and _usable_secret(settings.cloud_ai_api_key):
        return bool(settings.cloud_ai_fallback_model)
    return False


def _usable_secret(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    return value.strip() not in {"MediaOrganizer_API_Key", "YOUR_API_KEY", "PASTE_API_KEY_HERE"}


def _openai_compatible_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    prefix = "" if base.endswith("/v1") else "/v1"
    return f"{base}{prefix}/{path.lstrip('/')}"


def _preflight_prompt() -> str:
    return (
        "You are MediaForge OpenRouter chain preflight. "
        'Return only JSON: {"ok":true,"test":"mediaforge-preflight"}'
    )


def _chain_success_message(stage: str, model: str | None, attempts: int) -> str:
    title = "Быстрый анализ" if stage == "fast" else "Умная проверка" if stage == "smart" else "Цепочка моделей"
    return f"{title}: подключение успешно. Сработала модель: {model or '—'}. Попыток: {attempts}."
