import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.app_settings_repository import AppSettingsRepository
from ..schemas.settings import AppSettingsRead, AppSettingsUpdate, LocalModelsResult, TestConnectionResult
from .tmdb_client import TmdbClient

_TMDB_TEST_TIMEOUT = 8.0
_LOCAL_AI_TIMEOUT = 5.0


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
        await self.repo.update(data)
        await self.session.commit()
        return await self.get_settings()

    async def test_tmdb(self, api_key: str | None = None) -> TestConnectionResult:
        s = await self.repo.get_or_create()
        key = api_key or s.tmdb_api_key
        if not key:
            return TestConnectionResult(success=False, message="TMDB API ключ не настроен")
        client = TmdbClient(key, timeout_seconds=_TMDB_TEST_TIMEOUT)
        try:
            results = await client.search_movie("The Matrix", year=1999)
            if results:
                return TestConnectionResult(success=True, message="TMDB подключён успешно")
            return TestConnectionResult(success=True, message="TMDB подключён (тестовый запрос вернул пустой результат)")
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


def _default_endpoint(provider: str) -> str:
    return "http://127.0.0.1:11434" if provider == "ollama" else "http://127.0.0.1:1234"


async def _test_gemini(api_key: str) -> TestConnectionResult:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        async with httpx.AsyncClient(timeout=_TMDB_TEST_TIMEOUT) as client:
            resp = await client.get(url)
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
            resp = await client.get(f"{base_url.rstrip('/')}/v1/models", headers=headers)
            if resp.status_code == 200:
                return TestConnectionResult(success=True, message="AI-сервис подключён успешно")
            return TestConnectionResult(success=False, message=f"AI-сервис вернул статус {resp.status_code}")
    except httpx.ConnectError:
        return TestConnectionResult(success=False, message=f"AI-сервис не отвечает по адресу {base_url}")
    except Exception as exc:
        return TestConnectionResult(success=False, message=str(exc))
