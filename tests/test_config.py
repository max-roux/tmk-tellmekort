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
    assert s.pertinence_thresholds == (0.50, 0.58, 0.65, 0.72)
    assert s.email_min_weighted == 3.5
    assert s.active_window_days == 90


def test_production_problems_only_on_https() -> None:
    local = Settings(_env_file=None, base_url="http://localhost:8000")  # type: ignore[call-arg]
    assert local.production_problems() == []
    bare = Settings(_env_file=None, base_url="https://papers.example.com")  # type: ignore[call-arg]
    problems = " ".join(bare.production_problems())
    assert "SECRET_KEY" in problems and "POSTMARK_SERVER_TOKEN or SMTP_HOST" in problems
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


def test_pertinence_thresholds_parse_and_must_ascend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERTINENCE_THRESHOLDS", "[0.2, 0.3, 0.45, 0.7]")
    assert Settings(_env_file=None).pertinence_thresholds == (0.2, 0.3, 0.45, 0.7)  # type: ignore[call-arg]
    monkeypatch.setenv("PERTINENCE_THRESHOLDS", "[0.5, 0.3, 0.45, 0.7]")
    with pytest.raises(ValueError, match="ascending"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_smtp_alone_is_enough_for_production() -> None:
    def gmail(**overrides: str) -> Settings:
        values = {
            "base_url": "https://papers.example.com",
            "secret_key": "a-long-random-value",
            "email_from": "tmkpapers@gmail.com",
            "smtp_host": "smtp.gmail.com",
            "smtp_username": "tmkpapers@gmail.com",
            "smtp_password": "app-pass",
        } | overrides
        return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]

    assert gmail().production_problems() == []
    assert "SMTP_PASSWORD" in " ".join(gmail(smtp_password="").production_problems())


def test_mailer_prefers_postmark_then_smtp_then_outbox() -> None:
    from app.email import mailer_for
    from app.email.outbox import OutboxMailer
    from app.email.postmark import PostmarkMailer
    from app.email.smtp import SmtpMailer

    base = {"email_from": "tmkpapers@gmail.com"}
    smtp = {"smtp_host": "smtp.gmail.com", "smtp_username": "u", "smtp_password": "p"}
    both = Settings(_env_file=None, postmark_server_token="pm", **base, **smtp)  # type: ignore[call-arg, arg-type]
    only_smtp = Settings(_env_file=None, **base, **smtp)  # type: ignore[call-arg, arg-type]
    neither = Settings(_env_file=None, **base)  # type: ignore[call-arg, arg-type]
    assert isinstance(mailer_for(both), PostmarkMailer)
    assert isinstance(mailer_for(only_smtp), SmtpMailer)
    assert isinstance(mailer_for(neither), OutboxMailer)


def test_half_set_smtp_falls_back_to_the_outbox() -> None:
    from app.email import mailer_for
    from app.email.outbox import OutboxMailer

    half = Settings(_env_file=None, smtp_host="smtp.gmail.com")  # type: ignore[call-arg]
    assert isinstance(mailer_for(half), OutboxMailer)
