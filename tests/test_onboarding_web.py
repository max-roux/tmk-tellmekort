from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts import magic_links
from app.accounts.users import add_user
from app.config import Settings, get_settings
from app.db.models import CriterionSettings, LlmSpend, ProfileVector, SeedPaper, Topic, User
from app.db.session import get_session
from app.main import create_app
from app.profiles.topics import TopicProposer
from app.web.deps import get_embedder, get_pubmed, get_topic_proposer
from tests.fakes import FakeEmbedder, FakeMessagesClient, FakePubMed, message

pytestmark = pytest.mark.db

SETTINGS = Settings(_env_file=None, secret_key="test-secret", base_url="https://maxfac.test")  # type: ignore[call-arg]


@pytest.fixture
def user(db_session: Session) -> User:
    return add_user(db_session, "surgeon@example.com")


@pytest.fixture
def pubmed() -> FakePubMed:
    return FakePubMed()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def proposer_client() -> FakeMessagesClient:
    return FakeMessagesClient([message("message_topics.json")])  # type: ignore[list-item]


def build_client(
    db_session: Session,
    user: User,
    *,
    embedder: FakeEmbedder | None,
    pubmed: FakePubMed,
    proposer: TopicProposer | None,
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_embedder] = lambda: embedder
    app.dependency_overrides[get_pubmed] = lambda: pubmed
    app.dependency_overrides[get_topic_proposer] = lambda: proposer
    client = TestClient(app, base_url="https://maxfac.test")
    client.post("/auth", data={"t": magic_links.issue(db_session, user, datetime.now(UTC))})
    return client


@pytest.fixture
def client(
    db_session: Session,
    user: User,
    embedder: FakeEmbedder,
    pubmed: FakePubMed,
    proposer_client: FakeMessagesClient,
) -> TestClient:
    proposer = TopicProposer(proposer_client, model="claude-sonnet-5-5")  # type: ignore[arg-type]
    return build_client(db_session, user, embedder=embedder, pubmed=pubmed, proposer=proposer)


def topic_form(rows: list[tuple[str, str, bool]]) -> dict[str, str]:
    form = {"count": str(len(rows))}
    for i, (label, description, keep) in enumerate(rows):
        form[f"label_{i}"], form[f"description_{i}"] = label, description
        if keep:
            form[f"keep_{i}"] = "on"
    return form


def test_full_onboarding_flow(
    client: TestClient, db_session: Session, user: User, pubmed: FakePubMed
) -> None:
    assert "Suggest topics" in client.get("/onboarding").text

    proposed = client.post("/onboarding/interests", data={"interests": "VSP, fibula, MRONJ, TMJ"})
    assert proposed.status_code == 200
    assert 'value="Orthognathic surgery: virtual surgical planning"' in proposed.text
    assert db_session.scalar(select(LlmSpend.usd)) is not None  # proposal cost recorded
    assert not db_session.scalars(select(Topic)).all()  # nothing saved before confirming

    form = topic_form(
        [
            ("Orthognathic surgery: virtual surgical planning", "VSP and CAD/CAM splints.", True),
            ("Medication-related osteonecrosis of the jaw", "MRONJ staging.", False),  # unticked
            ("Cleft lip and palate", "", True),  # added by hand, description defaults to label
            ("", "", False),
        ]
    )
    saved = client.post("/onboarding/topics", data=form, follow_redirects=False)
    assert saved.headers["location"] == "/onboarding/seeds"
    topics = {t.label: t for t in db_session.scalars(select(Topic))}
    assert set(topics) == {
        "Orthognathic surgery: virtual surgical planning",
        "Cleft lip and palate",
    }
    assert topics["Cleft lip and palate"].description == "Cleft lip and palate"
    assert all(t.embedding is not None and t.embedding_model == "voyage-4" for t in topics.values())
    assert db_session.get(ProfileVector, user.id) is not None

    seeds = client.post(
        "/onboarding/seeds",
        data={"refs": "42958619\n10.1016/j.oooo.2026.08.003\n42897076 99999999 junk"},
    )
    assert "Added 2 papers" in seeds.text
    assert "Not found on PubMed: 99999999" in seeds.text
    assert "not used: 42897076" in seeds.text
    assert "Not a PMID or DOI: junk" in seeds.text
    assert set(db_session.scalars(select(SeedPaper.pmid))) == {"42958619", "42963307"}

    removed = client.post("/onboarding/seeds/remove", data={"pmid": "42963307"})
    assert removed.status_code == 200
    assert set(db_session.scalars(select(SeedPaper.pmid))) == {"42958619"}

    weights = client.post(
        "/onboarding/weights",
        data={"w_pertinence": "2", "w_novelty": "0", "min_proof_strength": "3"},
        follow_redirects=False,
    )
    assert weights.headers["location"] == "/"
    cs = db_session.get(CriterionSettings, user.id)
    assert cs is not None
    assert (cs.w_pertinence, cs.w_novelty, cs.w_depth) == (2.0, 0.0, 1.0)
    assert cs.min_proof_strength == 3 and cs.min_depth is None
    assert cs.hide_case_reports is False  # unticked checkbox
    assert "set up" in client.get("/").text

    again = client.get("/onboarding/weights")
    assert (
        'id="w_pertinence" name="w_pertinence" min="0" max="5" step="0.5" value="2.0"' in again.text
    )


def test_topics_validation(client: TestClient) -> None:
    resp = client.post("/onboarding/topics", data=topic_form([("A", "a", False)]))
    assert resp.status_code == 422 and "at least one topic" in resp.text
    resp = client.post("/onboarding/topics", data={"count": "nonsense"})
    assert resp.status_code == 422


def test_weights_validation_keeps_input(client: TestClient) -> None:
    form = {
        f"w_{c}": "0"
        for c in ("pertinence", "proof_strength", "novelty", "depth", "practical_usefulness")
    }
    resp = client.post("/onboarding/weights", data=form)
    assert resp.status_code == 422 and "weight above zero" in resp.text


def test_without_proposer_or_embedder_onboarding_still_works(
    db_session: Session, user: User, pubmed: FakePubMed
) -> None:
    client = build_client(db_session, user, embedder=None, pubmed=pubmed, proposer=None)
    page = client.post("/onboarding/interests", data={"interests": "VSP"})
    assert "not set up" in page.text
    client.post("/onboarding/topics", data=topic_form([("VSP", "Virtual planning", True)]))
    topic = db_session.scalars(select(Topic)).one()
    assert topic.embedding is None  # embedded later by cli.py embed
    assert db_session.get(ProfileVector, user.id) is None


def test_proposal_failure_falls_back_to_manual(
    db_session: Session, user: User, pubmed: FakePubMed, embedder: FakeEmbedder
) -> None:
    failing = FakeMessagesClient([message("message_topics.json", stop_reason="refusal")])  # type: ignore[list-item]
    proposer = TopicProposer(failing, model="claude-sonnet-5-5")  # type: ignore[arg-type]
    client = build_client(db_session, user, embedder=embedder, pubmed=pubmed, proposer=proposer)
    page = client.post("/onboarding/interests", data={"interests": "VSP"})
    assert page.status_code == 200 and "Suggestions failed" in page.text


def test_pubmed_outage_on_seeds(db_session: Session, user: User, embedder: FakeEmbedder) -> None:
    client = build_client(
        db_session, user, embedder=embedder, pubmed=FakePubMed(fail=True), proposer=None
    )
    resp = client.post("/onboarding/seeds", data={"refs": "10.1016/abc"})
    assert resp.status_code == 502 and "PubMed did not answer" in resp.text


def test_empty_seeds_skip_to_weights(client: TestClient) -> None:
    resp = client.post("/onboarding/seeds", data={"refs": ""}, follow_redirects=False)
    assert resp.headers["location"] == "/onboarding/weights"
