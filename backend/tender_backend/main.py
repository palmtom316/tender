from fastapi import FastAPI

from tender_backend.api.files import router as files_router
from tender_backend.api.health import router as health_router
from tender_backend.api.parse import router as parse_router
from tender_backend.api.projects import router as projects_router
from tender_backend.api.requirements import router as requirements_router
from tender_backend.api.scoring import router as scoring_router
from tender_backend.api.search import router as search_router
from tender_backend.api.drafts import router as drafts_router
from tender_backend.api.review import router as review_router
from tender_backend.api.compliance import router as compliance_router
from tender_backend.api.table_overrides import router as table_overrides_router
from tender_backend.api.exports import router as exports_router
from tender_backend.core.config import get_settings
from tender_backend.core.logging import setup_logging
from tender_backend.core.middleware import RequestContextMiddleware


def create_app() -> FastAPI:
    settings = get_settings()

    json_logs = settings.app_env != "development"
    setup_logging(json_output=json_logs)

    app = FastAPI(title=settings.app_name, version=settings.version)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(projects_router, prefix=settings.api_prefix)
    app.include_router(files_router, prefix=settings.api_prefix)
    app.include_router(parse_router, prefix=settings.api_prefix)
    app.include_router(requirements_router, prefix=settings.api_prefix)
    app.include_router(scoring_router, prefix=settings.api_prefix)
    app.include_router(search_router, prefix=settings.api_prefix)
    app.include_router(drafts_router, prefix=settings.api_prefix)
    app.include_router(review_router, prefix=settings.api_prefix)
    app.include_router(compliance_router, prefix=settings.api_prefix)
    app.include_router(table_overrides_router, prefix=settings.api_prefix)
    app.include_router(exports_router, prefix=settings.api_prefix)
    return app


app = create_app()
