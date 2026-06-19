import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes.filesystem import router as filesystem_router
from .api.routes.health import router as health_router
from .api.routes.items import router as items_router
from .api.routes.operation_plans import router as operation_plans_router
from .api.routes.recognition import router as recognition_router
from .api.routes.recognition_memory import router as recognition_memory_router
from .api.routes.scan_sessions import router as scan_sessions_router
from .api.routes.settings import router as settings_router
from .api.routes.tv import router as tv_router

logger = logging.getLogger(__name__)

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

FRONTEND_ROUTE_PREFIXES = (
    "/sessions",
    "/setup",
    "/status",
    "/about",
)
FRONTEND_ROUTE_PATHS = {"/settings"}


def _candidate_static_dirs() -> list[Path]:
    configured = os.getenv("MEDIAFORGE_STATIC_DIR")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))

    project_root = Path(__file__).resolve().parents[2]
    base_dir = Path(getattr(sys, "_MEIPASS", project_root))
    candidates.extend(
        [
            base_dir / "frontend" / "dist",
            base_dir / "app" / "static",
            project_root / "frontend" / "dist",
            Path(__file__).resolve().parent / "static",
        ]
    )
    return candidates


def get_frontend_static_dir() -> Path | None:
    for candidate in _candidate_static_dirs():
        index = candidate / "index.html"
        if index.is_file():
            return candidate
    return None


def _accepts_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "application/xhtml+xml" in accept


def _is_frontend_route(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized == "/" or normalized in FRONTEND_ROUTE_PATHS or normalized.startswith(FRONTEND_ROUTE_PREFIXES)


def _index_response(static_dir: Path) -> FileResponse:
    return FileResponse(static_dir / "index.html")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Auto-create tables and apply column migrations on startup."""
    try:
        from .db.base import Base, import_models
        from .db.session import engine
        from backend.scripts.init_db import _apply_column_migrations

        import_models()  # registers all models with Base.metadata
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await _apply_column_migrations(conn)
    except Exception:
        logger.warning("Could not auto-initialise database", exc_info=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="MediaForge", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(filesystem_router)
    app.include_router(health_router)
    app.include_router(items_router)
    app.include_router(operation_plans_router)
    app.include_router(recognition_router)
    app.include_router(recognition_memory_router)
    app.include_router(scan_sessions_router)
    app.include_router(settings_router)
    app.include_router(tv_router)

    static_dir = get_frontend_static_dir()
    if static_dir is not None:
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.middleware("http")
        async def frontend_navigation_middleware(request: Request, call_next):
            if request.method == "GET" and _accepts_html(request) and _is_frontend_route(request.url.path):
                return _index_response(static_dir)
            return await call_next(request)

        @app.get("/{full_path:path}", include_in_schema=False)
        async def frontend_spa_fallback(full_path: str, request: Request):
            path = "/" + full_path
            if request.method == "GET" and _is_frontend_route(path):
                return _index_response(static_dir)
            raise HTTPException(status_code=404, detail="Not Found")
    return app


app = create_app()
