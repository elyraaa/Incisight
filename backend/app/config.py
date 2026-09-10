from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Incisight"
    environment: str = "development"
    database_url: str = "sqlite:///./incisight.db"
    assemblyai_api_key: str = ""
    assemblyai_agent_id: str = ""
    tool_api_secret: str = Field(default="dev-tool-secret-change-me", min_length=16)
    admin_api_secret: str = Field(default="dev-admin-secret-change-me", min_length=16)
    app_base_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:5173"
    llm_api_key: str = ""
    llm_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
