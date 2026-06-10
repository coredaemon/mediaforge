from fastapi import APIRouter, Query

from ...schemas.settings import BrowseResult
from ...services.filesystem_service import browse_directory, get_filesystem_roots

router = APIRouter(prefix="/filesystem", tags=["filesystem"])


@router.get("/roots", response_model=list[str])
async def list_roots() -> list[str]:
    return get_filesystem_roots()


@router.get("/browse", response_model=BrowseResult)
async def browse(path: str = Query(...)) -> BrowseResult:
    return browse_directory(path)
