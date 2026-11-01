from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts import magic_links
from app.config import get_settings
from app.db.models import CriterionSettings, User
from app.db.session import get_session
from app.feed import feedback
from app.jobs.weekly_ingest import store_papers
from app.main import create_app
from app.sources.pubmed import ParsedPaper
from app.web import feed as feed_routes
from tests.feed_setup import SETTINGS, TODAY, grade, user

pytestmark = pytest.mark.db
__all__ = ["user"]  # pytest fixture


@pytest.fixture
def client(db_session: Session, user: User, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # 10 liked papers scoring 5 everywhere, 4 read-but-not-liked scoring 2.
    papers = [
        ParsedPaper(f"9000{i:02d}", f"Paper {i}", "Abstract.", "J", date(2026, 10, 20))
        for i in range(14)
    ]
    store_papers(db_session, papers)
    for i, p in enumerate(papers):
        liked = i < 10
        grade(db_session, p.pmid, 5 if liked else 2)
        feedback.record(db_session, user.id, p.pmid, "like" if liked else "read", "app", SETTINGS)
    monkeypatch.setattr(feed_routes, "today", lambda: TODAY)
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    c = TestClient(app, base_url="https://maxfac.test")
    c.post("/auth", data={"t": magic_links.issue(db_session, user, datetime.now(UTC))})
    return c


def test_banner_suggests_and_one_click_applies(
    client: TestClient, db_session: Session, user: User
) -> None:
    html = client.get("/").text
    assert "Papers you like score high on proof strength" in html
    resp = client.post(
        "/suggestion/apply", data={"criterion": "proof_strength"}, follow_redirects=False
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/"
    db_session.expire_all()
    cs = db_session.get(CriterionSettings, user.id)
    assert cs is not None and cs.w_proof_strength == 2.0
    assert "score high on proof strength" not in client.get("/").text


def test_dismissed_suggestion_stays_away(
    client: TestClient, db_session: Session, user: User
) -> None:
    client.post("/suggestion/dismiss", data={"criterion": "proof_strength"})
    html = client.get("/").text
    assert "score high on proof strength" not in html
    assert "score high on novelty" in html  # the next widest gap (all tie here)
    db_session.expire_all()
    cs = db_session.get(CriterionSettings, user.id)
    assert cs is not None and cs.w_proof_strength == 1.0  # never changed silently


def test_unknown_criterion_rejected(client: TestClient) -> None:
    assert client.post("/suggestion/apply", data={"criterion": "vibes"}).status_code == 422
