from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...schemas.recognition import RecognitionPreflightResult
from ...services.recognition_clients import TitleNormalizerClient
from ...services.recognition_service import RecognitionService

router = APIRouter(prefix="/recognition", tags=["recognition"])


def get_local_preflight_client() -> TitleNormalizerClient | None:
    return None


def get_cloud_preflight_client() -> TitleNormalizerClient | None:
    return None


@router.post("/preflight", response_model=RecognitionPreflightResult)
async def recognition_preflight(
    session: AsyncSession = Depends(get_session),
    local_client: TitleNormalizerClient | None = Depends(get_local_preflight_client),
    cloud_client: TitleNormalizerClient | None = Depends(get_cloud_preflight_client),
) -> RecognitionPreflightResult:
    return await RecognitionService(session, local_client=local_client, gemini_client=cloud_client).preflight()
