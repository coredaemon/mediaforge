from collections.abc import Sequence

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...models.tmdb_match_candidate import TmdbMatchCandidate
from ...repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from ...schemas.tmdb import TmdbMatchCandidateRead

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/{item_id}/tmdb-candidates", response_model=list[TmdbMatchCandidateRead])
async def list_item_tmdb_candidates(
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> Sequence[TmdbMatchCandidate]:
    return await TmdbMatchCandidateRepository(session).list_by_media_item(item_id)
