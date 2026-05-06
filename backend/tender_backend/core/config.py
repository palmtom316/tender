from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tender Backend"
    app_env: str = "development"
    api_prefix: str = "/api"
    database_url: str | None = None
    evidence_upload_dir: Path = Path(__file__).resolve().parents[2] / "data" / "master_data_assets"
    evidence_upload_max_bytes: int = 50 * 1024 * 1024
    tender_document_storage_root: Path = Path(__file__).resolve().parents[2] / "data" / "tender_documents"
    tender_document_upload_max_bytes: int = 200 * 1024 * 1024
    template_render_root: Path = Path("/tmp/tender_template_renders")
    template_bundle_root: Path = Path("/tmp/tender_template_bundles")
    standard_ocr_worker_count: int = 1
    standard_mineru_model_version: str = "vlm"
    standard_mineru_language: str = "ch"
    standard_mineru_enable_table: bool = True
    standard_mineru_enable_formula: bool = False
    standard_mineru_is_ocr: bool = True
    standard_mineru_page_ranges: str | None = None
    standard_mineru_timeout_seconds: float = 600.0
    standard_ai_worker_count: int = 4
    standard_ai_scope_delay_ms: int = 200
    standard_ai_scope_delay_jitter_ms: int = 200
    standard_ai_gateway_timeout_seconds: float = 120.0
    standard_repair_enabled: bool = True
    vision_max_concurrent_pages: int = 1
    vision_page_dpi: int = 200
    vision_page_delay_ms: int = 0
    vision_ai_gateway_timeout_seconds: float = 300.0
    vl_repair_max_concurrent_tasks: int = 1
    vl_repair_page_dpi: int = 200
    vl_repair_page_delay_ms: int = 0
    vl_repair_ai_gateway_timeout_seconds: float = 300.0
    ai_gateway_shared_secret: str = ""
    template_import_roots: str = ""
    version: str = "1.0.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
