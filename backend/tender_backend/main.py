from contextlib import asynccontextmanager

from fastapi import FastAPI

from tender_backend.core.threadpool_compat import apply_threadpool_compat
from tender_backend.api.files import router as files_router
from tender_backend.api.health import router as health_router
from tender_backend.api.parse import router as parse_router
from tender_backend.api.projects import router as projects_router
from tender_backend.api.requirements import router as requirements_router
from tender_backend.api.scoring import router as scoring_router
from tender_backend.api.search import router as search_router
from tender_backend.api.drafts import router as drafts_router
from tender_backend.api.equipment_selection import router as equipment_selection_router
from tender_backend.api.personnel_selection import router as personnel_selection_router
from tender_backend.api.review import router as review_router
from tender_backend.api.compliance import router as compliance_router
from tender_backend.api.table_overrides import router as table_overrides_router
from tender_backend.api.exports import router as exports_router
from tender_backend.api.settings import router as settings_router
from tender_backend.api.auth import router as auth_router
from tender_backend.api.tender_documents import router as tender_documents_router
from tender_backend.api.standards import router as standards_router
from tender_backend.api.users import router as users_router
from tender_backend.api.template_packages import router as template_packages_router
from tender_backend.api.master_data import router as master_data_router
from tender_backend.api.template_bindings import router as template_bindings_router
from tender_backend.api.bid_outline import router as bid_outline_router
from tender_backend.api.bid_generation import router as bid_generation_router
from tender_backend.api.charts import router as charts_router
from tender_backend.api.post_bid import router as post_bid_router
from tender_backend.api.deviation_table import router as deviation_table_router
from tender_backend.api.project_template_instances import router as project_template_instances_router
from tender_backend.core.config import get_settings
from tender_backend.core.logging import setup_logging
from tender_backend.core.middleware import RequestContextMiddleware
from tender_backend.services.norm_service.standard_processing_scheduler import (
    ensure_standard_processing_scheduler_started,
)

apply_threadpool_compat()


def create_app() -> FastAPI:
    settings = get_settings()

    json_logs = settings.app_env != "development"
    setup_logging(json_output=json_logs)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.database_url:
            ensure_standard_processing_scheduler_started()
        yield

    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(projects_router, prefix=settings.api_prefix)
    app.include_router(files_router, prefix=settings.api_prefix)
    app.include_router(parse_router, prefix=settings.api_prefix)
    app.include_router(requirements_router, prefix=settings.api_prefix)
    app.include_router(scoring_router, prefix=settings.api_prefix)
    app.include_router(search_router, prefix=settings.api_prefix)
    app.include_router(drafts_router, prefix=settings.api_prefix)
    app.include_router(equipment_selection_router, prefix=settings.api_prefix)
    app.include_router(personnel_selection_router, prefix=settings.api_prefix)
    app.include_router(review_router, prefix=settings.api_prefix)
    app.include_router(compliance_router, prefix=settings.api_prefix)
    app.include_router(table_overrides_router, prefix=settings.api_prefix)
    app.include_router(exports_router, prefix=settings.api_prefix)
    app.include_router(settings_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(tender_documents_router, prefix=settings.api_prefix)
    app.include_router(users_router, prefix=settings.api_prefix)
    app.include_router(standards_router, prefix=settings.api_prefix)
    app.include_router(template_packages_router, prefix=settings.api_prefix)
    app.include_router(master_data_router, prefix=settings.api_prefix)
    app.include_router(template_bindings_router, prefix=settings.api_prefix)
    app.include_router(bid_outline_router, prefix=settings.api_prefix)
    app.include_router(bid_generation_router, prefix=settings.api_prefix)
    app.include_router(charts_router, prefix=settings.api_prefix)
    app.include_router(post_bid_router, prefix=settings.api_prefix)
    app.include_router(deviation_table_router, prefix=settings.api_prefix)
    app.include_router(project_template_instances_router, prefix=settings.api_prefix)

    return app


app = create_app()
