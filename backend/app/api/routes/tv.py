from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...schemas.operation_plan import OperationPlanRead
from ...schemas.tmdb import TmdbSearchResult
from ...schemas.tv import (
    TvAnalyzeResult,
    TvEpisodeRead,
    TvManualLookupRequest,
    TvManualSearchRequest,
    TvReviewDecisionRequest,
    TvSeasonRead,
    TvShowRead,
)
from ...services.planning_service import NoMatchedItemsError
from ...services.scan_session_service import ScanSessionNotFoundError
from ...services.tmdb_client import (
    TmdbApiKeyMissingError,
    TmdbAuthError,
    TmdbClientProtocol,
    TmdbRateLimitError,
    TmdbUnavailableError,
)
from ...services.tv_analysis_service import TvAnalysisService, TvEpisodeNotFoundError, TvShowNotFoundError
from ...services.tv_planning_service import TvPlanningService

router = APIRouter(tags=["tv"])


def get_tmdb_client() -> TmdbClientProtocol | None:
    return None


def get_local_tv_client() -> object | None:
    return None


def get_gemini_tv_client() -> object | None:
    return None


@router.post("/scan-sessions/{session_id}/analyze-tv", response_model=TvAnalyzeResult)
async def analyze_scan_session_tv(
    session_id: int,
    force: bool = True,
    session: AsyncSession = Depends(get_session),
    tmdb_client: TmdbClientProtocol | None = Depends(get_tmdb_client),
    local_client: object | None = Depends(get_local_tv_client),
    gemini_client: object | None = Depends(get_gemini_tv_client),
) -> TvAnalyzeResult:
    try:
        return await TvAnalysisService(
            session,
            tmdb_client=tmdb_client,
            local_client=local_client,
            gemini_client=gemini_client,
        ).analyze_scan_session(session_id, force=force)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TmdbApiKeyMissingError, TmdbAuthError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TmdbRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TmdbUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/scan-sessions/{session_id}/tv-shows", response_model=list[TvShowRead])
async def list_scan_session_tv_shows(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> Sequence:
    try:
        return await TvAnalysisService(session).list_shows(session_id)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/scan-sessions/{session_id}/plan-tv", response_model=OperationPlanRead)
async def create_scan_session_tv_plan(
    session_id: int,
    force: bool = False,
    session: AsyncSession = Depends(get_session),
) -> OperationPlanRead:
    try:
        return await TvPlanningService(session).create_plan_for_scan_session(session_id, force=force)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoMatchedItemsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tv-shows/{show_id}", response_model=TvShowRead)
async def get_tv_show(show_id: int, session: AsyncSession = Depends(get_session)):
    try:
        return await TvAnalysisService(session).get_show(show_id)
    except TvShowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tv-shows/{show_id}/seasons", response_model=list[TvSeasonRead])
async def list_tv_show_seasons(show_id: int, session: AsyncSession = Depends(get_session)):
    try:
        await TvAnalysisService(session).get_show(show_id)
        return await TvAnalysisService(session).tv.list_seasons(show_id)
    except TvShowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tv-shows/{show_id}/episodes", response_model=list[TvEpisodeRead])
async def list_tv_show_episodes(show_id: int, session: AsyncSession = Depends(get_session)):
    try:
        await TvAnalysisService(session).get_show(show_id)
        return await TvAnalysisService(session).tv.list_episodes(show_id)
    except TvShowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tv-shows/{show_id}/tmdb-search", response_model=list[TmdbSearchResult])
async def search_tv_show_tmdb(
    show_id: int,
    payload: TvManualSearchRequest,
    session: AsyncSession = Depends(get_session),
    tmdb_client: TmdbClientProtocol | None = Depends(get_tmdb_client),
) -> Sequence[TmdbSearchResult]:
    try:
        return await TvAnalysisService(session, tmdb_client=tmdb_client).search_show_tmdb(
            show_id,
            query=payload.query,
            year=payload.year,
        )
    except TvShowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TmdbApiKeyMissingError, TmdbAuthError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TmdbRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TmdbUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/tv-shows/{show_id}/tmdb-lookup", response_model=TvShowRead)
async def lookup_tv_show_tmdb(
    show_id: int,
    payload: TvManualLookupRequest,
    session: AsyncSession = Depends(get_session),
    tmdb_client: TmdbClientProtocol | None = Depends(get_tmdb_client),
) -> TvShowRead:
    try:
        return await TvAnalysisService(session, tmdb_client=tmdb_client).lookup_show_tmdb(
            show_id,
            tmdb_id=payload.tmdb_id,
            imdb_id=payload.imdb_id,
            tvdb_id=payload.tvdb_id,
            select=payload.select,
        )
    except TvShowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TmdbRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TmdbUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (TmdbApiKeyMissingError, TmdbAuthError, ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tv-episodes/{episode_id}/acknowledge", response_model=TvEpisodeRead)
async def acknowledge_tv_episode(
    episode_id: int,
    session: AsyncSession = Depends(get_session),
) -> TvEpisodeRead:
    try:
        return await TvAnalysisService(session).acknowledge_episode(episode_id)
    except TvEpisodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tv-shows/{show_id}/review-decision", response_model=TvShowRead)
async def review_tv_show(
    show_id: int,
    payload: TvReviewDecisionRequest,
    session: AsyncSession = Depends(get_session),
) -> TvShowRead:
    try:
        return await TvAnalysisService(session).apply_review_decision(show_id, payload)
    except TvShowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
