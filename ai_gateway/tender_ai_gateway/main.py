from fastapi import FastAPI

from tender_ai_gateway.api.chat import router as chat_router
from tender_ai_gateway.api.credentials import router as credentials_router
from tender_ai_gateway.api.health import router as health_router
from tender_ai_gateway.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(chat_router, prefix=settings.api_prefix)
    app.include_router(credentials_router, prefix=settings.api_prefix)
    return app


app = create_app()
