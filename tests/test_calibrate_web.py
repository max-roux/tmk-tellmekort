import random
import re
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_session
from app.grading.grader import Grader
from app.jobs.calibration import create_sample, current_items, grade_set
from app.jobs.weekly_ingest import store_papers
from app.main import create_app
from app.sources.pubmed import parse_pubmed_xml
from app.web import access
from tests.conftest import FIXTURES
from tests.fakes import FakeAnthropic, message

pytestmark = pytest.mark.db

SETTINGS = Settings(_env_file=None, secret_key="test-secret", base_url="https://maxfac.test")  # type: ignore[call-arg]
SAMPLE = parse_pubmed_xml((FIXTURES / "pubmed" / "efetch_sample.xml").read_bytes()).papers
SCORES = {"proof_strength": "3", "novelty": "2", "depth": "4", "practical_usefulness": "3"}
MODEL_JUSTIFICATION = "Directly informs graft choice"


@pytest.fixture
def session(db_session: Session) -> Session:
    store_papers(db_session, SAMPLE)
    create_sample(db_session, 3, date(2026, 11, 1), random.Random(0), window_days=90)
    grader = Grader(FakeAnthropic(sync=[message()] * 3), model="claude-sonnet-5-5", effort="low")  # type: ignore[arg-type]
    grade_set(db_session, grader, date(2026, 11, 1))
    return db_session


@pytest.fixture
def client(session: Session) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    return TestClient(app, base_url="https://maxfac.test")


def enter(client: TestClient) -> None:
    resp = client.post(
        "/admin/calibrate/enter", data={"t": access.make_token(SETTINGS)}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/calibrate"


def test_link_puts_token_in_fragment_not_query() -> None:
    link = access.make_link(SETTINGS)
    assert link.startswith("https://maxfac.test/admin/calibrate/enter#")
    assert "?" not in link


def test_pages_denied_without_access(client: TestClient, session: Session) -> None:
    item = current_items(session)[0]
    assert client.get("/admin/calibrate").status_code == 403
    assert client.get(f"/admin/calibrate/{item.id}").status_code == 403
    assert client.post(f"/admin/calibrate/{item.id}", data=SCORES).status_code == 403


def test_bad_or_foreign_token_rejected(client: TestClient) -> None:
    other = Settings(_env_file=None, secret_key="other")  # type: ignore[call-arg]
    for t in ("", "garbage", access.make_token(other)):
        assert client.post("/admin/calibrate/enter", data={"t": t}).status_code == 403


def test_enter_sets_secure_httponly_cookie(client: TestClient) -> None:
    resp = client.post(
        "/admin/calibrate/enter", data={"t": access.make_token(SETTINGS)}, follow_redirects=False
    )
    cookie = resp.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Path=/admin/calibrate" in cookie


def test_enter_page_reads_fragment_client_side(client: TestClient) -> None:
    html = client.get("/admin/calibrate/enter").text
    assert "location.hash" in html and 'method="post"' in html


def test_overview_and_blind_item_page(client: TestClient, session: Session) -> None:
    enter(client)
    overview = client.get("/admin/calibrate")
    assert overview.status_code == 200
    assert "0 of 3" in overview.text

    item = current_items(session)[0]
    page = client.get(f"/admin/calibrate/{item.id}").text
    assert "Paper 1 of 3" in page
    assert "Proof strength" in page and "Systematic review/meta-analysis of RCTs" in page
    assert 'name="practical_usefulness" value="5"' in page
    # Blind: the model's justifications and scores never reach the page.
    assert MODEL_JUSTIFICATION not in page
    assert "model" not in page.lower().replace("model's scores are hidden", "")


def test_save_moves_to_next_ungraded_then_overview(client: TestClient, session: Session) -> None:
    enter(client)
    items = current_items(session)
    for n, item in enumerate(items):
        resp = client.post(
            f"/admin/calibrate/{item.id}",
            data={**SCORES, "comment": "thin stats"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        expected = (
            f"/admin/calibrate/{items[n + 1].id}" if n + 1 < len(items) else "/admin/calibrate"
        )
        assert resp.headers["location"] == expected
    for item in items:
        session.refresh(item)
        assert item.surgeon_scores == {
            "proof_strength": 3,
            "novelty": 2,
            "depth": 4,
            "practical_usefulness": 3,
            "comment": "thin stats",
        }
    assert "3 of 3" in client.get("/admin/calibrate").text


def test_missing_score_rerenders_with_error(client: TestClient, session: Session) -> None:
    enter(client)
    item = current_items(session)[0]
    resp = client.post(f"/admin/calibrate/{item.id}", data={"novelty": "2", "comment": "kept"})
    assert resp.status_code == 422
    assert "Pick a score for every criterion." in resp.text
    assert re.search(r'name="novelty" value="2"[^>]*checked', resp.text)
    assert "kept" in resp.text
    session.refresh(item)
    assert item.surgeon_scores is None
