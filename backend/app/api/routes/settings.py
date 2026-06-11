from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...schemas.settings import (
    AppSettingsRead,
    AppSettingsUpdate,
    CloudAiTestRequest,
    CloudModelsRequest,
    CloudModelsResult,
    LocalModelsResult,
    TestConnectionResult,
)
from ...schemas.recognition import LlmPreflightCheck
from ...services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettingsRead)
async def get_settings(session: AsyncSession = Depends(get_session)) -> AppSettingsRead:
    return await SettingsService(session).get_settings()


@router.put("", response_model=AppSettingsRead)
async def update_settings(
    payload: AppSettingsUpdate,
    session: AsyncSession = Depends(get_session),
) -> AppSettingsRead:
    return await SettingsService(session).update_settings(payload)


@router.post("/test-tmdb", response_model=TestConnectionResult)
async def test_tmdb(
    api_key: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> TestConnectionResult:
    return await SettingsService(session).test_tmdb(api_key=api_key)


@router.post("/test-ai", response_model=TestConnectionResult)
async def test_ai(session: AsyncSession = Depends(get_session)) -> TestConnectionResult:
    return await SettingsService(session).test_ai()


@router.post("/cloud-ai/models", response_model=CloudModelsResult)
async def get_cloud_ai_models(
    payload: CloudModelsRequest,
    session: AsyncSession = Depends(get_session),
) -> CloudModelsResult:
    return await SettingsService(session).get_cloud_models(payload)


@router.post("/cloud-ai/test", response_model=LlmPreflightCheck | TestConnectionResult)
async def test_cloud_ai(
    payload: CloudAiTestRequest,
    session: AsyncSession = Depends(get_session),
) -> LlmPreflightCheck | TestConnectionResult:
    return await SettingsService(session).test_cloud_ai(payload)


@router.get("/local-ai/ollama/models", response_model=LocalModelsResult)
async def get_ollama_models(
    endpoint: str = Query(default="http://127.0.0.1:11434"),
    session: AsyncSession = Depends(get_session),
) -> LocalModelsResult:
    return await SettingsService(session).get_ollama_models(endpoint=endpoint)


@router.get("/local-ai/lmstudio/models", response_model=LocalModelsResult)
async def get_lmstudio_models(
    endpoint: str = Query(default="http://127.0.0.1:1234"),
    session: AsyncSession = Depends(get_session),
) -> LocalModelsResult:
    return await SettingsService(session).get_lmstudio_models(endpoint=endpoint)
