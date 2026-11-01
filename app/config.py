from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-insecure-change-me"


class Settings(BaseSettings):
    """All runtime configuration. See SPEC.md §15."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://tmk:tmk@localhost:5432/tmk"
    secret_key: str = DEV_SECRET_KEY
    base_url: str = "http://localhost:8000"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    grading_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    voyage_api_key: str = ""
    embedding_model: str = "voyage-4"
    ncbi_api_key: str = ""
    ncbi_email: str = ""
    ncbi_tool: str = "tmk-recommender"
    postmark_server_token: str = ""
    # SMTP fallback when there is no Postmark token, e.g. Gmail with an app password.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    admin_email: str = ""

    grade_limit_per_week: int = 100
    fulltext_max_tokens: int = 12_000
    llm_monthly_cap_usd: float = 30.0
    pertinence_gate: float = 0.30
    # Pertinence cosine needed for scores 2, 3, 4 and 5 (SPEC.md §8.2); ascending.
    # Set from the first real run: graded papers' cosines span ~0.55-0.71 (10th-90th pct).
    pertinence_thresholds: tuple[float, float, float, float] = (0.50, 0.58, 0.65, 0.72)
    email_min_weighted: float = 3.2
    active_window_days: int = 90
    # Profile vector coefficients (SPEC.md §8.1); the not-for-me term is subtracted.
    profile_coef_topics: float = 1.0
    profile_coef_seeds: float = 1.0
    profile_coef_liked: float = 0.5
    profile_coef_not_for_me: float = 0.3

    @property
    def is_production(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def email_provider(self) -> str:
        """Who delivers our email, for the privacy note (SPEC.md §16)."""
        if self.postmark_server_token or not self.smtp_host:
            return "Postmark"
        return "Google (Gmail)" if "gmail" in self.smtp_host else self.smtp_host

    def production_problems(self) -> list[str]:
        """Settings that would make a public deployment silently insecure or broken."""
        if not self.is_production:
            return []
        problems = []
        if self.secret_key in ("", DEV_SECRET_KEY, "change-me"):
            problems.append("SECRET_KEY is unset or a placeholder (anyone could forge sessions)")
        problems += self._mail_problems()
        if not self.email_from:
            problems.append("EMAIL_FROM is unset")
        return problems

    def _mail_problems(self) -> list[str]:
        if self.postmark_server_token:
            return []
        if not self.smtp_host:
            return [
                "POSTMARK_SERVER_TOKEN or SMTP_HOST must be set (sign-in emails would not be sent)"
            ]
        return [
            f"{name} is unset"
            for name, value in (
                ("SMTP_USERNAME", self.smtp_username),
                ("SMTP_PASSWORD", self.smtp_password),
            )
            if not value
        ]

    @field_validator("pertinence_thresholds")
    @classmethod
    def _ascending(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        if list(v) != sorted(v):
            raise ValueError("pertinence thresholds must be ascending")
        return v

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
