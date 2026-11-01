"""Feed, library, history, feedback and disputes against a real database."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.users import add_user
from app.db.models import ProfileVector, ScoreDispute, User
from app.feed import feedback, queries
from app.grading.rubric import RUBRIC_VERSION
from app.jobs.weekly_ingest import store_papers
from tests.fakes import PUBMED_SAMPLE
from tests.feed_setup import SETTINGS, TODAY, grade, user

pytestmark = pytest.mark.db
__all__ = ["user"]  # pytest fixture


def feed(session: Session, user: User) -> list[queries.FeedItem]:
    return queries.feed(session, user.id, SETTINGS, TODAY)


def test_feed_ranks_graded_pertinent_papers(db_session: Session, user: User) -> None:
    grade(db_session, "42963182", 3)  # Orofacial..., closest to the topic
    grade(db_session, "42949936", 4)  # Pink lipoma, better scores
    grade(db_session, "42963307", 5)  # How clinicians think, cos 0.55: still above the gate
    grade(db_session, "42958619", 5)  # random vector: off topic, below the gate
    grade(db_session, "42746924", 5, rubric=RUBRIC_VERSION - 1)  # stale rubric: ineligible
    items = feed(db_session, user)
    assert [i.pmid for i in items] == ["42963307", "42949936", "42963182"]
    top = items[0]
    assert top.ranked.scores["pertinence"] == 2  # cos 0.55: past 0.50, short of 0.58
    assert top.grade.summary == "Summary." and top.paper.journal


def test_feedback_moves_papers_between_feed_library_and_history(
    db_session: Session, user: User
) -> None:
    for pmid in ("42963182", "42949936", "42963307"):
        grade(db_session, pmid, 4)
    feedback.record(db_session, user.id, "42963182", "like", "app", SETTINGS)
    feedback.record(db_session, user.id, "42949936", "read", "app", SETTINGS)
    feedback.record(db_session, user.id, "42963307", "not_for_me", "app", SETTINGS)

    assert [i.pmid for i in feed(db_session, user)] == ["42963182"]  # liked stays in the feed
    assert [i.pmid for i in queries.shelf(db_session, user.id, "library")] == ["42963182"]
    history = queries.shelf(db_session, user.id, "history")
    assert {(i.pmid, i.state.read, i.state.dismissed) for i in history} == {
        ("42949936", True, False),
        ("42963307", False, True),
    }

    feedback.record(db_session, user.id, "42963307", "undismiss", "app", SETTINGS)
    feedback.record(db_session, user.id, "42949936", "unread", "app", SETTINGS)
    assert len(feed(db_session, user)) == 3
    assert queries.shelf(db_session, user.id, "history") == []


def test_like_and_dismiss_reshape_the_profile_vector(db_session: Session, user: User) -> None:
    before = list(db_session.get(ProfileVector, user.id).vector)  # type: ignore[union-attr]
    feedback.record(db_session, user.id, "42963307", "like", "app", SETTINGS)
    db_session.expire_all()
    after_like = list(db_session.get(ProfileVector, user.id).vector)  # type: ignore[union-attr]
    assert after_like != before
    feedback.record(db_session, user.id, "42963307", "unlike", "app", SETTINGS)
    db_session.expire_all()
    restored = list(db_session.get(ProfileVector, user.id).vector)  # type: ignore[union-attr]
    assert restored == pytest.approx(before, abs=1e-6)


def test_unknown_feedback_kind_rejected(db_session: Session, user: User) -> None:
    with pytest.raises(ValueError):
        feedback.record(db_session, user.id, "42963182", "love", "app", SETTINGS)


def test_paper_detail_and_dispute(db_session: Session, user: User) -> None:
    grade(db_session, "42963182", 3)
    item = queries.paper(db_session, user.id, "42963182", SETTINGS)
    assert item is not None and item.ranked.scores["proof_strength"] == 3
    assert queries.paper(db_session, user.id, "00000000", SETTINGS) is None

    feedback.dispute(db_session, user.id, "42963182", "proof_strength", 5, "It is an RCT")
    feedback.dispute(db_session, user.id, "42963182", "pertinence", None, "")
    rows = db_session.scalars(select(ScoreDispute).order_by(ScoreDispute.created_at)).all()
    assert [(r.criterion, r.user_score, r.comment) for r in rows] == [
        ("proof_strength", 5, "It is an RCT"),
        ("pertinence", None, ""),
    ]
    assert rows[0].grade_id == item.grade.id
    with pytest.raises(ValueError):
        feedback.dispute(db_session, user.id, "42963182", "elegance", 3, "")
    with pytest.raises(LookupError):
        feedback.dispute(db_session, user.id, "42958619", "depth", 3, "")  # ungraded


def test_feed_is_empty_without_a_profile_vector(db_session: Session) -> None:
    store_papers(db_session, PUBMED_SAMPLE.papers)
    u = add_user(db_session, "new@example.com")
    grade(db_session, "42963182", 5)
    assert queries.feed(db_session, u.id, SETTINGS, TODAY) == []
