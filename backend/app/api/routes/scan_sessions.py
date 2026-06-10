from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...models.media_file import MediaFile
from ...models.media_item import MediaItem
from ...models.operation_plan import OperationPlan
from ...models.scan_session import ScanSession
from ...repositories.media_file_repository import MediaFileRepository
from ...repositories.media_item_repository import MediaItemRepository
from ...schemas.media_file import MediaFileRead
from ...schemas.media_item import MediaItemRead
from ...schemas.operation_plan import OperationPlanRead
from ...schemas.scan_session import ScanSessionCreate, ScanSessionListItem, ScanSessionRead
from ...schemas.tmdb import TmdbMatchResult
from ...services.parser_service import ParserService
from ...services.planning_service import NoMatchedItemsError, PlanningService
from ...services.scan_session_service import ScanSessionNotFoundError, ScanSessionService
from ...services.scanner_service import ScannerService
from ...services.tmdb_client import TmdbApiKeyMissingError, TmdbClientProtocol
from ...services.tmdb_service import TMDBService

router = APIRouter(prefix="/scan-sessions", tags=["scan-sessions"])


def get_tmdb_client() -> TmdbClientProtocol | None:
    return None


@router.post("", response_model=ScanSessionRead)
async def create_scan_session(
    payload: ScanSessionCreate,
    session: AsyncSession = Depends(get_session),
) -> ScanSession:
    return await ScanSessionService(session).create_scan_session(
        source_path=payload.source_path,
        target_path=payload.target_path,
    )


@router.get("", response_model=list[ScanSessionListItem])
async def list_scan_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> Sequence[ScanSession]:
    return await ScanSessionService(session).list_scan_sessions(limit=limit)


@router.get("/{session_id}", response_model=ScanSessionRead)
async def get_scan_session(session_id: int, session: AsyncSession = Depends(get_session)) -> ScanSession:
    try:
        return await ScanSessionService(session).get_scan_session(session_id)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/discover", response_model=ScanSessionRead)
async def discover_scan_session(session_id: int, session: AsyncSession = Depends(get_session)) -> ScanSession:
    try:
        return await ScannerService(session).discover(session_id)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/files", response_model=list[MediaFileRead])
async def list_scan_session_files(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> Sequence[MediaFile]:
    try:
        await ScanSessionService(session).get_scan_session(session_id)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await MediaFileRepository(session).list_for_scan_session(session_id)


@router.post("/{session_id}/parse", response_model=ScanSessionRead)
async def parse_scan_session(session_id: int, session: AsyncSession = Depends(get_session)) -> ScanSession:
    try:
        return await ParserService(session).parse_scan_session(session_id)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/items", response_model=list[MediaItemRead])
async def list_scan_session_items(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> Sequence[MediaItem]:
    try:
        await ScanSessionService(session).get_scan_session(session_id)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await MediaItemRepository(session).list_by_scan_session(session_id)


@router.post("/{session_id}/match-tmdb", response_model=TmdbMatchResult)
async def match_scan_session_tmdb(
    session_id: int,
    force: bool = False,
    session: AsyncSession = Depends(get_session),
    tmdb_client: TmdbClientProtocol | None = Depends(get_tmdb_client),
) -> TmdbMatchResult:
    try:
        return await TMDBService(session, client=tmdb_client).match_scan_session(session_id, force=force)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TmdbApiKeyMissingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/plan", response_model=OperationPlanRead)
async def create_scan_session_plan(
    session_id: int,
    force: bool = False,
    session: AsyncSession = Depends(get_session),
) -> OperationPlanRead:
    try:
        return await PlanningService(session).create_plan_for_scan_session(session_id, force=force)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoMatchedItemsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}/plans", response_model=list[OperationPlanRead])
async def list_scan_session_plans(
    session_id: int,
    session: AsyncSession = Depends(get_session),
) -> Sequence[OperationPlan]:
    try:
        return await PlanningService(session).list_plans_for_scan_session(session_id)
    except ScanSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
