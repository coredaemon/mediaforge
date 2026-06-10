from fastapi import FastAPI

from .api.routes.health import router as health_router
from .api.routes.scan_sessions import router as scan_sessions_router


def create_app() -> FastAPI:
    app = FastAPI(title="MediaForge")
    app.include_router(health_router)
    app.include_router(scan_sessions_router)
    return app


app = create_app()
