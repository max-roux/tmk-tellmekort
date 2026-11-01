from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Grade, GradingBatch, LlmSpend
from app.grading.grader import Grader
from app.grading.rubric import RUBRIC_VERSION
from app.jobs.grade_papers import (
    BatchTimeoutError,
    Polling,
    grade_batch,
    grade_sync,
    ungraded_pmids,
)
from app.jobs.weekly_ingest import store_papers
from app.sources.pubmed import parse_pubmed_xml
from tests.conftest import FIXTURES
from tests.fakes import FakeAnthropic, batch_lines, message

pytestmark = pytest.mark.db

TODAY = date(2026, 11, 1)
SAMPLE = parse_pubmed_xml((FIXTURES / "pubmed" / "efetch_sample.xml").read_bytes()).papers
BATCH_PMIDS = ["42958619", "42963182", "42949936", "42963307"]


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.now += s


@pytest.fixture
def session(db_session: Session) -> Session:
    store_papers(db_session, SAMPLE)
    return db_session


def grader(fake: FakeAnthropic) -> Grader:
    return Grader(fake, model="claude-sonnet-5-5", effort="low")  # type: ignore[arg-type]


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def spend(session: Session) -> Decimal:
    row = session.get(LlmSpend, date(2026, 11, 1))
    return row.usd if row else Decimal(0)


def test_ungraded_newest_first(session: Session) -> None:
    pmids = ungraded_pmids(session, limit=10)
    assert len(pmids) == 5
    assert pmids[-1] == "42746924"  # oldest entrez date in the fixture


def test_grade_sync_stores_grade_and_spend_and_is_idempotent(session: Session) -> None:
    fake = FakeAnthropic(sync=[message()])
    stats = grade_sync(session, grader(fake), ["42958619"], TODAY)

    assert (stats.graded, stats.retried, stats.failed) == (1, 0, [])
    g = session.scalars(select(Grade)).one()
    assert (g.pmid, g.rubric_version, g.model, g.input_source) == (
        "42958619",
        RUBRIC_VERSION,
        "claude-sonnet-5-5",
        "abstract",
    )
    assert (g.proof_strength, g.depth) == (4, 4)  # depth clamped: abstract only
    assert g.input_tokens == 2310 + 1180 and g.output_tokens == 612
    assert spend(session) == stats.usd > 0

    again = grade_sync(session, grader(fake), ["42958619"], TODAY)
    assert again.graded == 0
    assert len(fake.beta.messages.calls) == 1  # type: ignore[attr-defined]


def test_grade_sync_retries_once_then_gives_up(session: Session) -> None:
    refusal = message("message_refusal.json")
    fake = FakeAnthropic(sync=[refusal, message(), refusal, refusal])
    stats = grade_sync(session, grader(fake), ["42958619", "42963182"], TODAY)
    assert stats.graded == 1
    assert stats.retried == 2
    assert len(stats.failed) == 1
    assert count(session, Grade) == 1
    assert spend(session) > 0  # refusals still billed


def test_grade_batch_stores_results_retries_failures_and_marks_collected(
    session: Session,
) -> None:
    # Batch: 1 good, 1 invalid, 1 errored, 1 expired. The 3 failures are retried
    # individually: two succeed, one is refused again.
    fake = FakeAnthropic(
        batch_results=batch_lines(),
        polls_until_ended=2,
        sync=[message(), message(), message("message_refusal.json")],
    )
    t = FakeTime()
    stats = grade_batch(
        session, grader(fake), BATCH_PMIDS, TODAY, Polling(sleep=t.sleep, clock=t.clock)
    )

    assert stats.submitted == 4
    assert stats.graded == 3
    assert stats.retried == 3
    assert len(stats.failed) == 1
    assert t.now == 120  # two polls at 60 s
    batch = session.scalars(select(GradingBatch)).one()
    assert batch.status == "collected" and batch.ended_at is not None
    assert batch.input_sources == {p: "abstract" for p in BATCH_PMIDS}
    assert count(session, Grade) == 3
    assert spend(session) == stats.usd


def test_grade_batch_resumes_open_batch_without_resubmitting(session: Session) -> None:
    t = FakeTime()
    slow = FakeAnthropic(batch_results=batch_lines(), polls_until_ended=10**6)
    with pytest.raises(BatchTimeoutError):
        grade_batch(
            session,
            grader(slow),
            BATCH_PMIDS,
            TODAY,
            Polling(sleep=t.sleep, clock=t.clock, timeout=300),
        )
    assert session.scalars(select(GradingBatch.status)).one() == "submitted"

    # Next run: the open batch has finished; it is collected and nothing new is submitted.
    rerun = FakeAnthropic(batch_results=batch_lines(), sync=[message()] * 3)
    stats = grade_batch(
        session, grader(rerun), BATCH_PMIDS, TODAY, Polling(sleep=t.sleep, clock=t.clock)
    )
    assert rerun.messages.batches.created == []  # type: ignore[attr-defined]
    assert stats.submitted == 0
    assert count(session, Grade) == 4
    assert session.scalars(select(GradingBatch.status)).one() == "collected"
