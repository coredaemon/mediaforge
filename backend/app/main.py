import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    return app


app = create_app()
