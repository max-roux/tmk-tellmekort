from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.accounts import magic_links
from app.accounts.users import add_user
from app.config import Settings, get_settings
from app.db.models import LlmSpend, PipelineRun, User
from app.db.session import get_session
from app.email.base import EmailMessage
from app.feed import feedback
from app.main import create_app
from app.web import admin as admin_routes
from app.web.deps import get_mailer
from tests.feed_setup import grade, user

pytestmark = pytest.mark.db
__all__ = ["user"]  # pytest fixture

SETTINGS = Settings(  # type: ignore[call-arg]
    _env_file=None, secret_key="test-secret", base_url="https://maxfac.test", llm_monthly_cap_usd=30
)


class Mailer:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, m: EmailMessage) -> str:
        self.sent.append(m)
        return "pm"


@pytest.fixture
def mailer() -> Mailer:
    return Mailer()


@pytest.fixture
def app_client(db_session: Session, mailer: Mailer, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(admin_routes, "now", lambda: datetime(2026, 11, 1, 12, tzinfo=UTC))
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_mailer] = lambda: mailer
    return TestClient(app, base_url="https://maxfac.test")


def sign_in(client: TestClient, session: Session, u: User) -> None:
    client.post("/auth", data={"t": magic_links.issue(session, u, datetime.now(UTC))})


def test_admin_only(app_client: TestClient, db_session: Session, user: User) -> None:
    assert app_client.get("/admin", follow_redirects=False).headers["location"] == "/login"
    sign_in(app_client, db_session, user)  # an onboarded surgeon, not an admin
    assert app_client.get("/admin").status_code == 403
    assert app_client.post("/admin/send-test").status_code == 403


def test_dashboard_shows_runs_spend_disputes_and_calibration(
    app_client: TestClient, db_session: Session, user: User
) -> None:
    db_session.add(
        PipelineRun(
            started_at=datetime(2026, 11, 1, 1, tzinfo=UTC),
            finished_at=datetime(2026, 11, 1, 2, tzinfo=UTC),
            status="ok",
            stats={"ingest": {"stored": 87}, "grade": {"graded": 80, "dropped": 0}},
        )
    )
    db_session.add(LlmSpend(month=date(2026, 11, 1), usd=Decimal("12.5")))
    db_session.commit()
    grade(db_session, "42963182", 3)
    feedback.dispute(db_session, user.id, "42963182", "proof_strength", 5, "It is an RCT")
    admin = add_user(db_session, "admin@example.com", is_admin=True)
    sign_in(app_client, db_session, admin)

    html = app_client.get("/admin").text
    assert "ok" in html and "87" in html and "80" in html  # last run and its stats
    assert "$12.50" in html and "$30.00" in html and "42%" in html  # spend vs cap
    assert "It is an RCT" in html and "surgeon@example.com" in html
    assert "model 3" in html and "surgeon 5" in html  # the disputed score
    assert "No calibration scores yet" in html


def test_send_test_email_goes_to_the_admin(
    app_client: TestClient, db_session: Session, mailer: Mailer
) -> None:
    admin = add_user(db_session, "admin@example.com", is_admin=True)
    sign_in(app_client, db_session, admin)
    resp = app_client.post("/admin/send-test", follow_redirects=False)
    assert resp.status_code == 303
    assert [m.to for m in mailer.sent] == ["admin@example.com"]
    assert "Test email sent" in app_client.get(resp.headers["location"]).text
