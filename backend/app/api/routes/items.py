from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...models.tmdb_match_candidate import TmdbMatchCandidate
from ...repositories.media_item_repository import MediaItemRepository
from ...repositories.tmdb_match_candidate_repository import TmdbMatchCandidateRepository
from ...schemas.media_item import MediaItemRead
from ...schemas.recognition import RecognitionCorrectionCreate, RecognitionCorrectionRead
from ...schemas.review import ReviewDecisionRequest, TmdbManualLookupRequest, TmdbManualSearchRequest
from ...schemas.tmdb import TmdbMatchCandidateRead
from ...services.item_review_service import ItemReviewService
from ...services.recognition_service import MediaItemNotFoundError as RecognitionMediaItemNotFoundError
from ...services.recognition_service import RecognitionService
from ...services.tmdb_client import TmdbAuthError, TmdbRateLimitError, TmdbUnavailableError
from ...services.tmdb_service import (
    MediaItemNotFoundError,
    TMDBService,
    TmdbApiKeyMissingError,
    TmdbCandidateNotFoundError,
    TmdbCandidateOwnershipError,
    TmdbLookupError,
    TmdbLookupNotFoundError,
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


@router.post("/{item_id}/tmdb-search", response_model=list[TmdbMatchCandidateRead])
async def manual_tmdb_search(
    item_id: int,
    payload: TmdbManualSearchRequest,
    session: AsyncSession = Depends(get_session),
) -> Sequence[TmdbMatchCandidate]:
    try:
        return await TMDBService(session).manual_search(
            item_id,
            query=payload.query.strip(),
            year=payload.year,
            media_type=payload.media_type,
            language=payload.language,
        )
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TmdbApiKeyMissingError, TmdbAuthError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TmdbRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TmdbUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TmdbLookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{item_id}/tmdb-lookup", response_model=TmdbMatchCandidateRead)
async def manual_tmdb_lookup(
    item_id: int,
    payload: TmdbManualLookupRequest,
    session: AsyncSession = Depends(get_session),
) -> TmdbMatchCandidate:
    try:
        return await TMDBService(session).manual_lookup(
            item_id,
            tmdb_id=payload.tmdb_id,
            imdb_id=payload.imdb_id,
            tvdb_id=payload.tvdb_id,
            media_type=payload.media_type,
            select=False,
        )
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TmdbLookupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TmdbApiKeyMissingError, TmdbAuthError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TmdbRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TmdbUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TmdbLookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{item_id}/review-decision", response_model=MediaItemRead)
async def apply_review_decision(
    item_id: int,
    payload: ReviewDecisionRequest,
    session: AsyncSession = Depends(get_session),
) -> MediaItemRead:
    try:
        return await ItemReviewService(session).apply_review_decision(item_id, payload)
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TmdbLookupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TmdbLookupError as exc:
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
