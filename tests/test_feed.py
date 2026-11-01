"""Feed, library, history, feedback and disputes against a real database."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.users import add_user
from app.config import Settings
from app.db.models import Grade, ProfileVector, ScoreDispute, User
from app.domain.criteria import INTRINSIC_CRITERIA
from app.domain.preferences import Preferences
from app.feed import feedback, queries
from app.grading.rubric import RUBRIC_VERSION
from app.jobs.embed_papers import embed_papers
from app.jobs.weekly_ingest import store_papers
from app.profiles import service
from app.profiles.topics import ProposedTopic
from tests.fakes import PUBMED_SAMPLE, FakeEmbedder

pytestmark = pytest.mark.db

TODAY = date(2026, 11, 1)
SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
TOPIC = "fibula flap mandible reconstruction"
# Paper vectors relative to the single topic direction [1, 0]: cosines 0.99, 0.8, 0.55, 0.1.
PINNED = {
    TOPIC: [1.0, 0.0],
    "Orofacial Cleft Characteristics": [0.99, 0.141],
    "Pink lipoma": [0.8, 0.6],
    "How clinicians think": [0.55, 0.835],
}
EVEN = Preferences(
    weights=dict.fromkeys(("pertinence", *INTRINSIC_CRITERIA), 1.0),
    minimums=dict.fromkeys(("pertinence", *INTRINSIC_CRITERIA)),
    hide_case_reports=False,
)


def grade(session: Session, pmid: str, score: int, *, rubric: int = RUBRIC_VERSION) -> None:
    session.add(
        Grade(
            pmid=pmid,
            rubric_version=rubric,
            model="claude-sonnet-5-5",
            input_source="abstract",
            **dict.fromkeys(INTRINSIC_CRITERIA, score),
            justifications={c: f"{c} because" for c in INTRINSIC_CRITERIA},
            summary="Summary.",
            why_it_matters="Why.",
            study_design="cohort",
            input_tokens=1,
            output_tokens=1,
        )
    )
    session.commit()


@pytest.fixture
def user(db_session: Session) -> User:
    store_papers(db_session, PUBMED_SAMPLE.papers)
    e = FakeEmbedder(pinned=PINNED)
    embed_papers(db_session, e)
    u = add_user(db_session, "surgeon@example.com")
    service.replace_topics(db_session, u.id, [ProposedTopic("Fibula", TOPIC)], "onboarding")
    service.save_preferences(db_session, u.id, EVEN)
    assert service.sync_embeddings(db_session, e, u.id, service.coefficients(SETTINGS))
    return u


def titles(items: list[queries.FeedItem]) -> list[str]:
    return [i.paper.title.split()[0] for i in items]


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
    assert top.ranked.scores["pertinence"] == 4  # cos 0.55
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
    assert [i.pmid for i in queries.library(db_session, user.id)] == ["42963182"]
    history = queries.history(db_session, user.id)
    assert {(i.pmid, i.state.read, i.state.dismissed) for i in history} == {
        ("42949936", True, False),
        ("42963307", False, True),
    }

    feedback.record(db_session, user.id, "42963307", "undismiss", "app", SETTINGS)
    feedback.record(db_session, user.id, "42949936", "unread", "app", SETTINGS)
    assert len(feed(db_session, user)) == 3
    assert queries.history(db_session, user.id) == []


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
