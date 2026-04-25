from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tender AI Gateway"
    app_env: str = "development"
    api_prefix: str = "/api"
    version: str = "0.1.0"
    default_primary_model: str = "deepseek-v4-flash"
    default_fallback_model: str = "qwen-max"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_timeout: int = 60
    default_retry_count: int = 2

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
