from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...models.media_file import MediaFile
from ...models.scan_session import ScanSession
from ...repositories.media_file_repository import MediaFileRepository
from ...schemas.media_file import MediaFileRead
from ...schemas.scan_session import ScanSessionCreate, ScanSessionListItem, ScanSessionRead
from ...services.scan_session_service import ScanSessionNotFoundError, ScanSessionService
from ...services.scanner_service import ScannerService

router = APIRouter(prefix="/scan-sessions", tags=["scan-sessions"])


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
