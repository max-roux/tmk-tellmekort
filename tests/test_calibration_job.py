import random
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CalibrationItem
from app.grading.grader import Grader
from app.jobs import calibration, grade_papers
from app.jobs.calibration import (
    CalibrationSetExistsError,
    calibration_report,
    create_sample,
    current_items,
    grade_set,
    save_surgeon_scores,
)
from app.jobs.weekly_ingest import store_papers
from app.sources.pubmed import parse_pubmed_xml
from tests.conftest import FIXTURES
from tests.fakes import FakeAnthropic, message

pytestmark = pytest.mark.db

TODAY = date(2026, 11, 1)
SAMPLE = parse_pubmed_xml((FIXTURES / "pubmed" / "efetch_sample.xml").read_bytes()).papers
SURGEON = {"proof_strength": 3, "novelty": 3, "depth": 4, "practical_usefulness": 2}


@pytest.fixture
def session(db_session: Session) -> Session:
    store_papers(db_session, SAMPLE)
    return db_session


def grader(n_calls: int) -> Grader:
    return Grader(
        FakeAnthropic(sync=[message()] * n_calls), model="claude-sonnet-5-5", effort="low"
    )  # type: ignore[arg-type]


def test_create_sample_and_refuse_overwrite(session: Session) -> None:
    pmids = create_sample(session, 3, TODAY, random.Random(0), window_days=90)
    assert len(pmids) == 3
    assert {i.pmid for i in current_items(session)} == set(pmids)
    with pytest.raises(CalibrationSetExistsError):
        create_sample(session, 3, TODAY, random.Random(0), window_days=90)
    again = create_sample(session, 2, TODAY, random.Random(0), window_days=90, replace=True)
    assert len(again) == 2 and len(current_items(session)) == 2


def test_sample_respects_window(session: Session) -> None:
    # Fixture entrez dates: 2026-09-16 .. 2026-10-30. A 10-day window keeps only October 30/28.
    pmids = create_sample(session, 20, TODAY, random.Random(0), window_days=10)
    assert "42746924" not in pmids and len(pmids) == 4


def test_grade_set_snapshots_model_scores(session: Session) -> None:
    create_sample(session, 2, TODAY, random.Random(0), window_days=90)
    stats = grade_set(session, grader(2), TODAY)
    assert (stats.items, stats.with_model_scores, stats.grading.graded) == (2, 2, 2)
    for item in current_items(session):
        assert item.model_scores == {
            "proof_strength": 4,
            "novelty": 3,
            "depth": 4,  # clamped: abstract only
            "practical_usefulness": 4,
        }
    # Re-running costs nothing: grades exist.
    assert grade_set(session, grader(0), TODAY).grading.graded == 0


def test_surgeon_scores_validated_and_saved(session: Session) -> None:
    create_sample(session, 1, TODAY, random.Random(0), window_days=90)
    item = current_items(session)[0]
    with pytest.raises(ValueError):
        save_surgeon_scores(session, item.id, {**SURGEON, "depth": 6}, "")
    with pytest.raises(ValueError):
        save_surgeon_scores(session, item.id, {"novelty": 3}, "")
    save_surgeon_scores(session, item.id, SURGEON, "  short follow-up ")
    session.refresh(item)
    assert item.surgeon_scores == {**SURGEON, "comment": "short follow-up"}


def test_report_and_carry_forward_on_rubric_bump(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_sample(session, 2, TODAY, random.Random(0), window_days=90)
    grade_set(session, grader(2), TODAY)
    for item in current_items(session):
        save_surgeon_scores(session, item.id, SURGEON, "")

    report, rows = calibration_report(session)
    assert report.n == 2
    worst = rows[report.disagreements[0].pmid]
    assert worst.justifications["practical_usefulness"].startswith("Directly informs")

    # Bump the rubric: v2 rows appear with surgeon scores carried over, model scores empty.
    for module in (calibration, grade_papers):
        monkeypatch.setattr(module, "RUBRIC_VERSION", 2)
    v2 = current_items(session)
    assert len(v2) == 2 and all(i.rubric_version == 2 for i in v2)
    assert all(i.surgeon_scores == {**SURGEON, "comment": ""} for i in v2)
    assert all(i.model_scores is None for i in v2)
    stats = grade_set(session, grader(2), TODAY)
    assert stats.grading.graded == 2  # regraded under v2
    versions = session.scalars(select(CalibrationItem.rubric_version).distinct()).all()
    assert sorted(versions) == [1, 2]
