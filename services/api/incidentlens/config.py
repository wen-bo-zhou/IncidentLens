from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "IncidentLens API"
    database_url: str = "sqlite:///data/runtime/incidentlens.db"
    redis_url: str = "redis://localhost:6379/0"
    task_mode: str = "inline"
    model_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_api_key: str = ""
    model_name: str = "qwen-plus"
    max_cost_cny: float = 0.20
    runner_daily_limit: int = 10
    runner_token: str = "runner-demo-token"
    admin_token: str = "admin-demo-token"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

