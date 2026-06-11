from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...models.tmdb_match_candidate import TmdbMatchCandidate
from ...repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from ...schemas.tmdb import TmdbMatchCandidateRead
from ...services.tmdb_service import (
    MediaItemNotFoundError,
    TMDBService,
    TmdbCandidateNotFoundError,
    TmdbCandidateOwnershipError,
)

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/{item_id}/tmdb-candidates", response_model=list[TmdbMatchCandidateRead])
async def list_item_tmdb_candidates(
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> Sequence[TmdbMatchCandidate]:
    return await TmdbMatchCandidateRepository(session).list_by_media_item(item_id)


@router.post(
    "/{item_id}/tmdb-candidates/{candidate_id}/select",
    response_model=TmdbMatchCandidateRead,
)
async def select_item_tmdb_candidate(
    item_id: int,
    candidate_id: int,
    session: AsyncSession = Depends(get_session),
) -> TmdbMatchCandidate:
    try:
        return await TMDBService(session).select_candidate(item_id, candidate_id)
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TmdbCandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TmdbCandidateOwnershipError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
