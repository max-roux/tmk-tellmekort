"""Shared setup for feed tests: an onboarded user whose single topic points at [1, 0]."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.accounts.users import add_user
from app.config import Settings
from app.db.models import Grade, User
from app.domain.criteria import ALL_CRITERIA, INTRINSIC_CRITERIA
from app.domain.preferences import Preferences
from app.grading.rubric import RUBRIC_VERSION
from app.jobs.embed_papers import embed_papers
from app.jobs.weekly_ingest import store_papers
from app.profiles import service
from app.profiles.topics import ProposedTopic
from tests.fakes import PUBMED_SAMPLE, FakeEmbedder

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
    weights=dict.fromkeys(ALL_CRITERIA, 1.0),
    minimums=dict.fromkeys(ALL_CRITERIA),
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


def onboarded_user(db_session: Session) -> User:
    store_papers(db_session, PUBMED_SAMPLE.papers)
    e = FakeEmbedder(pinned=PINNED)
    embed_papers(db_session, e)
    u = add_user(db_session, "surgeon@example.com")
    service.replace_topics(db_session, u.id, [ProposedTopic("Fibula", TOPIC)], "onboarding")
    service.save_preferences(db_session, u.id, EVEN)
    assert service.sync_embeddings(db_session, e, u.id, service.coefficients(SETTINGS))
    return u


@pytest.fixture
def user(db_session: Session) -> User:
    return onboarded_user(db_session)
