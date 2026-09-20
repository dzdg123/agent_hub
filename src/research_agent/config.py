from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    request_timeout_seconds: float = Field(default=60, gt=0, le=300)
    max_research_iterations: int = Field(default=2, ge=0, le=5)
    max_subqueries: int = Field(default=5, ge=1, le=10)
    max_concurrency: int = Field(default=3, ge=1, le=10)
    document_root: Path = Path("data/documents")
    database_path: Path = Path("data/agent.db")

    def prepare_directories(self) -> None:
        self.document_root.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.prepare_directories()
    return settings

