import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
    ],
)
def test_database_url_uses_psycopg(given: str, expected: str) -> None:
    assert Settings(database_url=given).database_url == expected


def test_spec_defaults() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.anthropic_model == "claude-sonnet-5-5"
    assert s.embedding_model == "voyage-4"
    assert s.grade_limit_per_week == 100
    assert s.pertinence_gate == 0.30
    assert s.email_min_weighted == 3.5
    assert s.active_window_days == 90


def test_production_problems_only_on_https() -> None:
    local = Settings(_env_file=None, base_url="http://localhost:8000")  # type: ignore[call-arg]
    assert local.production_problems() == []
    bare = Settings(_env_file=None, base_url="https://papers.example.com")  # type: ignore[call-arg]
    problems = " ".join(bare.production_problems())
    assert "SECRET_KEY" in problems and "POSTMARK_SERVER_TOKEN" in problems
    assert "EMAIL_FROM" in problems
    ready = Settings(  # type: ignore[call-arg]
        _env_file=None,
        base_url="https://papers.example.com",
        secret_key="a-long-random-value",
        postmark_server_token="pm",
        email_from="papers@mail.example.com",
    )
    assert ready.production_problems() == []


def test_app_refuses_to_start_misconfigured() -> None:
    from app.main import create_app

    bare = Settings(_env_file=None, base_url="https://papers.example.com")  # type: ignore[call-arg]
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(bare)
