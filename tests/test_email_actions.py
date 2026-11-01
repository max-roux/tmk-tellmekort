import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import EmailSend, Feedback, User
from app.db.session import get_session
from app.email import actions
from app.main import create_app
from tests.feed_setup import TODAY, grade, user

pytestmark = pytest.mark.db
__all__ = ["user"]  # pytest fixture

SETTINGS = Settings(_env_file=None, secret_key="test-secret", base_url="https://tmk.test")  # type: ignore[call-arg]
PMID = "42963182"


@pytest.fixture
def send(db_session: Session, user: User) -> EmailSend:
    grade(db_session, PMID, 4)
    row = EmailSend(user_id=user.id, week_of=TODAY, missed_pmid=PMID)
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def client(db_session: Session) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    return TestClient(app, base_url="https://tmk.test")  # not signed in


def token(user: User, send: EmailSend, action: str = "like") -> str:
    return actions.make_token(SETTINGS, user.id, PMID, action, send.id)


def test_link_puts_token_in_fragment(user: User, send: EmailSend) -> None:
    link = actions.action_link(SETTINGS, user.id, PMID, "read", send.id)
    assert link.startswith("https://tmk.test/a/read#") and "?" not in link


def test_token_roundtrip_and_rejections(user: User, send: EmailSend) -> None:
    parsed = actions.read_token(SETTINGS, token(user, send, "not_for_me"))
    assert parsed == actions.EmailAction(user.id, PMID, "not_for_me", send.id)
    other = Settings(_env_file=None, secret_key="other")  # type: ignore[call-arg]
    assert actions.read_token(other, token(user, send)) is None
    assert actions.read_token(SETTINGS, "garbage") is None
    assert actions.read_token(SETTINGS, token(user, send), max_age=-1) is None  # expired
    with pytest.raises(ValueError):
        actions.make_token(SETTINGS, user.id, PMID, "unread", send.id)  # not an email action


def test_opening_the_link_records_nothing(
    client: TestClient, db_session: Session, user: User, send: EmailSend
) -> None:
    page = client.get("/a/like")
    assert page.status_code == 200 and 'action="/a"' in page.text
    # Nothing submits by itself: a scanner that runs scripts still records nothing.
    assert ".submit()" not in page.text
    assert '<button class="button" type="submit">Like this paper</button>' in page.text
    assert db_session.scalars(select(Feedback)).all() == []
    assert client.get("/a/delete").status_code == 404


def test_post_records_once_per_send_without_sign_in(
    client: TestClient, db_session: Session, user: User, send: EmailSend
) -> None:
    for _ in range(2):  # a double tap, or a scanner and a human
        resp = client.post("/a", data={"t": token(user, send)})
        assert resp.status_code == 200 and "Saved" in resp.text
    rows = db_session.scalars(select(Feedback)).all()
    assert [(r.kind, r.source, r.send_id) for r in rows] == [("like", "email", send.id)]


def test_bad_or_stale_tokens_are_refused(
    client: TestClient, db_session: Session, user: User, send: EmailSend
) -> None:
    assert client.post("/a", data={"t": "garbage"}).status_code == 400
    gone = actions.make_token(SETTINGS, uuid.uuid4(), PMID, "like", send.id)  # deleted user
    assert client.post("/a", data={"t": gone}).status_code == 400
    assert db_session.scalars(select(Feedback)).all() == []
