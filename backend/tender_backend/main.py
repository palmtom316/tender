from fastapi import FastAPI

from tender_backend.api.files import router as files_router
from tender_backend.api.health import router as health_router
from tender_backend.api.projects import router as projects_router
from tender_backend.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(projects_router, prefix=settings.api_prefix)
    app.include_router(files_router, prefix=settings.api_prefix)
    return app


app = create_app()
