from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. See SPEC.md §15."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://maxfac:maxfac@localhost:5432/maxfac"
    secret_key: str = "dev-insecure-change-me"
    base_url: str = "http://localhost:8000"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    grading_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    voyage_api_key: str = ""
    embedding_model: str = "voyage-4"
    ncbi_api_key: str = ""
    ncbi_email: str = ""
    ncbi_tool: str = "maxfac-recommender"
    postmark_server_token: str = ""
    email_from: str = ""
    admin_email: str = ""

    grade_limit_per_week: int = 100
    fulltext_max_tokens: int = 12_000
    llm_monthly_cap_usd: float = 30.0
    pertinence_gate: float = 0.30
    email_min_weighted: float = 3.5
    active_window_days: int = 90

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, v: str) -> str:
        # Render and most hosts hand out postgres:// or postgresql:// URLs;
        # SQLAlchemy needs the explicit psycopg (v3) driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v.removeprefix(prefix)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
