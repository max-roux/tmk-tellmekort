import random
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts import magic_links
from app.accounts.users import add_user
from app.config import Settings, get_settings
from app.db.session import get_session
from app.grading.grader import Grader
from app.jobs.calibration import create_sample, current_items, grade_set
from app.jobs.weekly_ingest import store_papers
from app.main import create_app
from app.sources.pubmed import parse_pubmed_xml
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


def enter(client: TestClient, session: Session, **flags: bool) -> None:
    """Sign in as the surgeon, a calibrator unless flags say otherwise."""
    user = add_user(session, "surgeon@example.com", **(flags or {"can_calibrate": True}))
    token = magic_links.issue(session, user, datetime.now(UTC))
    assert client.post("/auth", data={"t": token}, follow_redirects=False).status_code == 303


def test_anonymous_goes_to_login(client: TestClient, session: Session) -> None:
    item = current_items(session)[0]
    for resp in (
        client.get("/admin/calibrate", follow_redirects=False),
        client.get(f"/admin/calibrate/{item.id}", follow_redirects=False),
        client.post(f"/admin/calibrate/{item.id}", data=SCORES, follow_redirects=False),
    ):
        assert resp.status_code == 303 and resp.headers["location"] == "/login"


def test_signed_in_without_permission_is_refused(client: TestClient, session: Session) -> None:
    enter(client, session, is_admin=False)
    item = current_items(session)[0]
    assert client.get("/admin/calibrate").status_code == 403
    assert client.post(f"/admin/calibrate/{item.id}", data=SCORES).status_code == 403
    session.refresh(item)
    assert item.surgeon_scores is None


def test_admins_may_calibrate(client: TestClient, session: Session) -> None:
    enter(client, session, is_admin=True)
    assert client.get("/admin/calibrate").status_code == 200


def test_calibrators_see_a_link_from_any_page(client: TestClient, session: Session) -> None:
    enter(client, session)
    assert 'href="/admin/calibrate"' in client.get("/onboarding").text


def test_overview_and_blind_item_page(client: TestClient, session: Session) -> None:
    enter(client, session)
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
    enter(client, session)
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
    enter(client, session)
    item = current_items(session)[0]
    resp = client.post(f"/admin/calibrate/{item.id}", data={"novelty": "2", "comment": "kept"})
    assert resp.status_code == 422
    assert "Pick a score for every criterion." in resp.text
    assert re.search(r'name="novelty" value="2"[^>]*checked', resp.text)
    assert "kept" in resp.text
    session.refresh(item)
    assert item.surgeon_scores is None
