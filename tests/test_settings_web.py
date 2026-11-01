from collections.abc import Iterator
from datetime import UTC, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts import magic_links
from app.config import get_settings
from app.db.models import (
    EmailSend,
    Feedback,
    LoginAttempt,
    ProfileVector,
    Topic,
    User,
)
from app.db.session import get_session
from app.feed import feedback
from app.main import create_app
from tests.feed_setup import SETTINGS, TODAY, grade, user

pytestmark = pytest.mark.db
__all__ = ["user"]  # pytest fixture


@pytest.fixture
def client(db_session: Session, user: User) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    c = TestClient(app, base_url="https://tmk.test")
    c.post("/auth", data={"t": magic_links.issue(db_session, user, datetime.now(UTC))})
    return c


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_settings_show_and_save_the_schedule(
    client: TestClient, db_session: Session, user: User
) -> None:
    page = client.get("/settings").text
    assert "Europe/Copenhagen" in page and 'value="06:30"' in page
    resp = client.post(
        "/settings",
        data={"send_weekday": "2", "send_local_time": "07:15", "timezone": "Europe/Paris"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    db_session.refresh(user)
    assert (user.send_weekday, user.send_local_time, user.timezone) == (
        2,
        time(7, 15),
        "Europe/Paris",
    )


@pytest.mark.parametrize(
    "form",
    [
        {"send_weekday": "7", "send_local_time": "07:15", "timezone": "Europe/Paris"},
        {"send_weekday": "1", "send_local_time": "25:00", "timezone": "Europe/Paris"},
        {"send_weekday": "1", "send_local_time": "07:15", "timezone": "Mars/Olympus"},
    ],
)
def test_bad_settings_are_refused(
    client: TestClient, db_session: Session, user: User, form: dict[str, str]
) -> None:
    assert client.post("/settings", data=form).status_code == 422
    db_session.refresh(user)
    assert user.timezone == "Europe/Copenhagen"


def test_delete_needs_confirmation_then_removes_everything(
    client: TestClient, db_session: Session, user: User
) -> None:
    grade(db_session, "42963182", 4)
    feedback.record(db_session, user.id, "42963182", "like", "app", SETTINGS)
    db_session.add(EmailSend(user_id=user.id, week_of=TODAY, missed_pmid="42963182"))
    db_session.add(LoginAttempt(email=user.email, created_at=datetime.now(UTC)))
    db_session.commit()

    assert client.post("/settings/delete", data={"confirm": "nope"}).status_code == 422
    assert count(db_session, User) == 1

    resp = client.post("/settings/delete", data={"confirm": "delete"}, follow_redirects=False)
    assert resp.status_code == 303 and 'session=""' in resp.headers["set-cookie"]
    db_session.expire_all()
    for model in (User, Topic, ProfileVector, Feedback, EmailSend, LoginAttempt):
        assert count(db_session, model) == 0, model.__name__
    assert "Sign in" in client.get("/").text  # signed out
