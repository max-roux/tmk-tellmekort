from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Grade, LlmSpend, PipelineRun
from app.email.base import EmailMessage
from app.grading.grader import Grader
from app.jobs.grade_papers import Polling
from app.jobs.weekly_pipeline import Clients, run_weekly
from tests.fakes import FakeAnthropic, FakeEmbedder, FakePubMed, batch_lines, message

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 1, 1, 0, tzinfo=UTC)  # Sunday 02:00 Copenhagen
SETTINGS = Settings(_env_file=None, admin_email="admin@example.com")  # type: ignore[call-arg]
# Batch fixture: one success is an invalid grade, one errors, one expires: 3 retried one by one.
RETRIES = 3


class Mailer:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, m: EmailMessage) -> str:
        self.sent.append(m)
        return "pm"


def clients(mailer: Mailer, pubmed: FakePubMed | None = None, retries: int = RETRIES) -> Clients:
    fake = FakeAnthropic(sync=[message()] * retries, batch_results=batch_lines())
    grader = Grader(fake, model="claude-sonnet-5-5", effort="low")  # type: ignore[arg-type]
    return Clients(pubmed or FakePubMed(), FakeEmbedder(), grader, mailer)  # type: ignore[arg-type]


def grades(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Grade)) or 0


def subjects(mailer: Mailer) -> list[str]:
    return [m.subject for m in mailer.sent]


def run(session: Session, settings: Settings, c: Clients) -> PipelineRun:
    return run_weekly(session, settings, c, NOW, poll=Polling(sleep=lambda s: None))


def test_full_run_ingests_embeds_narrows_grades_and_records(db_session: Session) -> None:
    mailer = Mailer()
    r = run(db_session, SETTINGS, clients(mailer))
    assert r.status == "ok" and r.finished_at is not None and r.error is None
    assert r.stats["ingest"]["stored"] == 4  # 14-day window: the September paper is outside
    assert r.stats["embed"]["papers"] == 4
    assert r.stats["narrow"]["selected"] == 4
    assert r.stats["grade"]["kept"] == 4 and r.stats["grade"]["dropped"] == 0
    assert grades(db_session) == 4
    assert mailer.sent == []  # nothing to alert

    again = run(db_session, SETTINGS, clients(mailer, retries=0))
    assert again.stats["ingest"]["stored"] == 0 and again.stats["grade"]["kept"] == 0
    assert grades(db_session) == 4


def test_cap_grades_only_what_fits_and_alerts(db_session: Session) -> None:
    db_session.add(LlmSpend(month=date(2026, 11, 1), usd=Decimal("29.995")))
    db_session.commit()
    mailer = Mailer()
    r = run(db_session, SETTINGS.model_copy(update={"llm_monthly_cap_usd": 30.0}), clients(mailer))
    assert r.status == "ok"
    assert r.stats["grade"]["kept"] < 4 and r.stats["grade"]["dropped"] > 0
    assert any("cap" in s.lower() for s in subjects(mailer))


def test_crossing_80_percent_alerts_once(db_session: Session) -> None:
    db_session.add(LlmSpend(month=date(2026, 11, 1), usd=Decimal("23.99")))
    db_session.commit()
    mailer = Mailer()
    run(db_session, SETTINGS, clients(mailer))
    assert [s for s in subjects(mailer) if "80%" in s]


def test_failure_is_recorded_alerted_and_raised(db_session: Session) -> None:
    mailer = Mailer()
    with pytest.raises(Exception, match="down"):
        run(db_session, SETTINGS, clients(mailer, pubmed=FakePubMed(fail=True)))
    r = db_session.scalars(select(PipelineRun)).one()
    assert r.status == "failed" and "down" in (r.error or "")
    assert any("failed" in s.lower() for s in subjects(mailer))
