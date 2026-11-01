from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Grade, LlmSpend
from app.email.base import EmailMessage
from app.grading.grader import Grader
from app.grading.rubric import RUBRIC_VERSION
from app.jobs.grade_papers import Polling
from app.jobs.regrade import regrade, stale_pmids
from app.jobs.weekly_ingest import store_papers
from tests.fakes import PUBMED_SAMPLE, FakeAnthropic, FakePubMed, message
from tests.feed_setup import grade

pytestmark = pytest.mark.db

TODAY = date(2026, 11, 1)
SETTINGS = Settings(_env_file=None, admin_email="admin@example.com")  # type: ignore[call-arg]
OLD = RUBRIC_VERSION - 1
NO_WAIT = Polling(sleep=lambda s: None)


class Mailer:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, m: EmailMessage) -> str:
        self.sent.append(m)
        return "pm"


def batch_line(pmid: str) -> dict:  # type: ignore[type-arg]
    return {"custom_id": pmid, "result": {"type": "succeeded", "message": message()}}


@pytest.fixture
def session(db_session: Session) -> Session:
    store_papers(db_session, PUBMED_SAMPLE.papers)
    grade(db_session, "42963182", 3, rubric=OLD)  # 2026-10-30: stale, in the window
    grade(db_session, "42949936", 3, rubric=OLD)  # 2026-10-28: stale, in the window
    grade(db_session, "42746924", 3, rubric=OLD)  # 2026-09-16: stale, outside 30 days
    grade(db_session, "42963307", 3, rubric=OLD)
    grade(db_session, "42963307", 4)  # already has a current grade
    return db_session


def test_stale_papers_are_those_in_window_without_a_current_grade(session: Session) -> None:
    assert stale_pmids(session, since=date(2026, 10, 2)) == ["42963182", "42949936"]  # newest first
    assert len(stale_pmids(session, since=date(2026, 8, 1))) == 3


def test_regrade_grades_stale_papers_and_keeps_old_rows(session: Session) -> None:
    fake = FakeAnthropic(batch_results=[batch_line("42963182"), batch_line("42949936")])
    grader = Grader(fake, model="claude-sonnet-5-5", effort="low")  # type: ignore[arg-type]
    stats = regrade(
        session,
        FakePubMed(),
        grader,
        Mailer(),
        SETTINGS,
        TODAY,  # type: ignore[arg-type]
        window_days=30,
        poll=NO_WAIT,
    )
    assert (stats["todo"], stats["graded"]) == (2, 2)
    current = set(session.scalars(select(Grade.pmid).where(Grade.rubric_version == RUBRIC_VERSION)))
    assert current == {"42963182", "42949936", "42963307"}
    assert len(session.scalars(select(Grade).where(Grade.rubric_version == OLD)).all()) == 4


def test_regrade_respects_the_spend_cap(session: Session) -> None:
    session.add(LlmSpend(month=date(2026, 11, 1), usd=Decimal("30")))
    session.commit()
    mailer = Mailer()
    grader = Grader(FakeAnthropic(), model="claude-sonnet-5-5", effort="low")  # type: ignore[arg-type]
    stats = regrade(
        session,
        FakePubMed(),
        grader,
        mailer,
        SETTINGS,
        TODAY,  # type: ignore[arg-type]
        window_days=30,
        poll=NO_WAIT,
    )
    assert (stats["kept"], stats["dropped"]) == (0, 2)
    assert any("cap" in m.subject.lower() for m in mailer.sent)
