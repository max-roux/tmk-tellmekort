from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts import magic_links
from app.config import get_settings
from app.db.models import Feedback, ScoreDispute, User
from app.db.session import get_session
from app.main import create_app
from app.web import feed as feed_routes
from tests.feed_setup import SETTINGS, TODAY, grade, user

pytestmark = pytest.mark.db
__all__ = ["user"]  # pytest fixture

TOP, MID, LOW = "42963307", "42949936", "42963182"  # ranked order once graded below


@pytest.fixture
def client(db_session: Session, user: User, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    grade(db_session, TOP, 5)
    grade(db_session, MID, 4)
    grade(db_session, LOW, 3)
    monkeypatch.setattr(feed_routes, "today", lambda: TODAY)
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    c = TestClient(app, base_url="https://maxfac.test")
    c.post("/auth", data={"t": magic_links.issue(db_session, user, datetime.now(UTC))})
    return c


def pmids_in(html: str) -> list[str]:
    import re

    return re.findall(r'data-pmid="(\d+)"', html)


def test_feed_shows_ranked_cards_with_scores_and_actions(client: TestClient) -> None:
    html = client.get("/").text
    assert pmids_in(html) == [TOP, MID, LOW]
    assert "Summary." in html and "Why." in html
    assert "Graded from abstract" in html
    for label in ("Pertinence", "Proof strength", "Novelty", "Depth", "Practical usefulness"):
        assert label in html
    assert 'value="like"' in html and 'value="read"' in html and 'value="not_for_me"' in html


def test_feedback_from_feed_returns_to_feed_and_hides_read(
    client: TestClient, db_session: Session
) -> None:
    resp = client.post(
        f"/paper/{TOP}/feedback", data={"kind": "read", "next": "/"}, follow_redirects=False
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/"
    assert pmids_in(client.get("/").text) == [MID, LOW]
    assert db_session.scalars(select(Feedback.source)).all() == ["app"]
    assert TOP in client.get("/history").text


def test_like_shows_in_library_and_undo_from_history(client: TestClient) -> None:
    client.post(f"/paper/{MID}/feedback", data={"kind": "like", "next": "/"})
    client.post(f"/paper/{LOW}/feedback", data={"kind": "not_for_me", "next": "/"})
    assert pmids_in(client.get("/library").text) == [MID]
    history = client.get("/history").text
    assert pmids_in(history) == [LOW] and 'value="undismiss"' in history
    client.post(f"/paper/{LOW}/feedback", data={"kind": "undismiss", "next": "/history"})
    assert LOW in pmids_in(client.get("/").text)


def test_feedback_rejects_bad_kind_and_foreign_redirects(client: TestClient) -> None:
    assert client.post(f"/paper/{TOP}/feedback", data={"kind": "love"}).status_code == 422
    resp = client.post(
        f"/paper/{TOP}/feedback",
        data={"kind": "like", "next": "//evil.example.com/"},
        follow_redirects=False,
    )
    assert resp.headers["location"] == f"/paper/{TOP}"


def test_paper_page_shows_all_justifications_and_takes_disputes(
    client: TestClient, db_session: Session
) -> None:
    page = client.get(f"/paper/{TOP}")
    assert page.status_code == 200
    assert "proof_strength because" in page.text and "depth because" in page.text
    assert "https://pubmed.ncbi.nlm.nih.gov/" in page.text or "https://doi.org/" in page.text
    resp = client.post(
        f"/paper/{TOP}/dispute",
        data={"criterion": "novelty", "user_score": "2", "comment": "Done before"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "Thanks" in client.get(resp.headers["location"]).text
    row = db_session.scalars(select(ScoreDispute)).one()
    assert (row.criterion, row.user_score, row.comment) == ("novelty", 2, "Done before")
    bad = client.post(f"/paper/{TOP}/dispute", data={"criterion": "novelty", "user_score": "9"})
    assert bad.status_code == 422


def test_unknown_or_ungraded_paper_is_404(client: TestClient) -> None:
    assert client.get("/paper/42958619").status_code == 404
    assert client.post("/paper/42958619/dispute", data={"criterion": "depth"}).status_code == 404


def test_pages_need_sign_in(db_session: Session) -> None:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    c = TestClient(app, base_url="https://maxfac.test")
    for path in ("/library", "/history", f"/paper/{TOP}"):
        assert c.get(path, follow_redirects=False).headers["location"] == "/login"
    assert "Sign in" in c.get("/").text
