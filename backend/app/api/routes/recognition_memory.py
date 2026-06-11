from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...models.recognition_memory import RecognitionTokenRule
from ...repositories.recognition_memory_repository import RecognitionMemoryRepository
from ...schemas.recognition import RecognitionCorrectionRead, RecognitionTokenRuleRead
from ...services.recognition_service import _correction_read

router = APIRouter(prefix="/recognition-memory", tags=["recognition-memory"])


@router.get("/corrections", response_model=list[RecognitionCorrectionRead])
async def list_recognition_corrections(
    session: AsyncSession = Depends(get_session),
) -> list[RecognitionCorrectionRead]:
    corrections = await RecognitionMemoryRepository(session).list_corrections()
    return [_correction_read(correction) for correction in corrections]


@router.get("/token-rules", response_model=list[RecognitionTokenRuleRead])
async def list_recognition_token_rules(
    session: AsyncSession = Depends(get_session),
) -> list[RecognitionTokenRule]:
    return list(await RecognitionMemoryRepository(session).list_token_rules())
