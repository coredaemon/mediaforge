from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...models.tmdb_match_candidate import TmdbMatchCandidate
from ...repositories.media_item_repository import MediaItemRepository
from ...repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from ...schemas.recognition import RecognitionCorrectionCreate, RecognitionCorrectionRead
from ...schemas.tmdb import TmdbMatchCandidateRead
from ...services.recognition_service import MediaItemNotFoundError as RecognitionMediaItemNotFoundError
from ...services.recognition_service import RecognitionService
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
    candidates = list(await TmdbMatchCandidateRepository(session).list_by_media_item(item_id))
    if candidates:
        return candidates

    item = await MediaItemRepository(session).get_by_id(item_id)
    if item is None or item.tmdb_id is None:
        return []

    return [_memory_candidate_from_item(item)]


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


@router.post("/{item_id}/corrections", response_model=RecognitionCorrectionRead)
async def create_item_correction(
    item_id: int,
    payload: RecognitionCorrectionCreate,
    session: AsyncSession = Depends(get_session),
) -> RecognitionCorrectionRead:
    try:
        return await RecognitionService(session).create_correction(item_id, payload)
    except RecognitionMediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _memory_candidate_from_item(item) -> TmdbMatchCandidate:
    return TmdbMatchCandidate(
        id=-item.id,
        media_item_id=item.id,
        tmdb_id=item.tmdb_id or 0,
        media_type=item.tmdb_media_type or "movie",
        title=item.localized_title or item.matched_title or item.parsed_title or "",
        original_title=item.tmdb_original_title,
        overview=item.localized_overview,
        year=item.matched_year or item.year,
        poster_path=item.poster_path,
        backdrop_path=item.backdrop_path,
        poster_url=item.poster_url,
        backdrop_url=item.backdrop_url,
        imdb_id=item.imdb_id,
        tvdb_id=item.tvdb_id,
        wikidata_id=item.wikidata_id,
        metadata_language=item.metadata_language,
        overview_is_fallback=False,
        vote_average=None,
        popularity=None,
        score=item.match_confidence or 1.0,
        is_selected=True,
        created_at=datetime.now(UTC),
    )
