import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.accounts import magic_links
from app.accounts.users import add_user
from app.config import Settings, get_settings
from app.db.models import CriterionSettings, MagicLink
from app.db.session import get_session
from app.email.base import EmailMessage
from app.main import create_app
from app.web import sessions
from app.web.deps import get_mailer

pytestmark = pytest.mark.db

SETTINGS = Settings(_env_file=None, secret_key="test-secret", base_url="https://maxfac.test")  # type: ignore[call-arg]
EMAIL = "Surgeon@Example.com"


class CapturingMailer:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> str:
        self.sent.append(message)
        return f"m-{len(self.sent)}"


@pytest.fixture
def mailer() -> CapturingMailer:
    return CapturingMailer()


@pytest.fixture
def client(db_session: Session, mailer: CapturingMailer) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_mailer] = lambda: mailer
    return TestClient(app, base_url="https://maxfac.test")


def token_from(message: EmailMessage) -> str:
    m = re.search(r"https://maxfac\.test/auth#([\w-]+)", message.text)
    assert m, message.text
    return m.group(1)


def test_login_emails_a_fragment_link_to_known_users_only(
    client: TestClient, db_session: Session, mailer: CapturingMailer
) -> None:
    add_user(db_session, "surgeon@example.com")
    known = client.post("/login", data={"email": EMAIL})
    unknown = client.post("/login", data={"email": "stranger@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert "Check your email" in known.text and "Check your email" in unknown.text
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == "surgeon@example.com"
    token = token_from(mailer.sent[0])
    stored = db_session.scalars(select(MagicLink.token_hash)).all()
    assert stored == [magic_links.hash_token(token)]  # only the hash is kept


def test_login_rejects_blank_email(client: TestClient) -> None:
    assert client.post("/login", data={"email": "  "}).status_code == 422


def test_login_rate_limited_per_email(client: TestClient, db_session: Session) -> None:
    add_user(db_session, "surgeon@example.com")
    codes = [client.post("/login", data={"email": EMAIL}).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_global_rate_limit_and_window(db_session: Session) -> None:
    now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    for i in range(magic_links.GLOBAL_RATE_LIMIT):
        assert magic_links.allow_attempt(db_session, f"u{i}@x.com", now)
    assert not magic_links.allow_attempt(db_session, "new@x.com", now)
    later = now + timedelta(hours=1, seconds=1)
    assert magic_links.allow_attempt(db_session, "new@x.com", later)


def test_opening_link_does_not_consume_it_and_post_signs_in(
    client: TestClient, db_session: Session, mailer: CapturingMailer
) -> None:
    add_user(db_session, "surgeon@example.com")
    client.post("/login", data={"email": EMAIL})
    token = token_from(mailer.sent[0])

    page = client.get("/auth")  # what a mail scanner prefetching the link sees
    assert page.status_code == 200 and 'action="/auth"' in page.text

    resp = client.post("/auth", data={"t": token}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/onboarding"  # not onboarded yet
    cookie = resp.headers["set-cookie"]
    assert "session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie

    again = client.post("/auth", data={"t": token}, follow_redirects=False)
    assert again.status_code == 400  # single use


def test_onboarded_user_lands_on_home(client: TestClient, db_session: Session) -> None:
    user = add_user(db_session, "surgeon@example.com", name="Ana")
    db_session.add(CriterionSettings(user_id=user.id))
    db_session.commit()
    token = magic_links.issue(db_session, user, datetime.now(UTC))
    resp = client.post("/auth", data={"t": token}, follow_redirects=False)
    assert resp.headers["location"] == "/"
    home = client.get("/")
    assert "set up, Ana" in home.text
    assert client.get("/login", follow_redirects=False).status_code == 303


def test_expired_or_unknown_tokens_rejected(client: TestClient, db_session: Session) -> None:
    user = add_user(db_session, "surgeon@example.com")
    token = magic_links.issue(db_session, user, datetime.now(UTC) - timedelta(minutes=16))
    assert client.post("/auth", data={"t": token}).status_code == 400
    assert client.post("/auth", data={"t": "made-up"}).status_code == 400
    assert client.post("/auth", data={}).status_code == 400


def test_protected_pages_redirect_to_login_and_logout_clears(
    client: TestClient, db_session: Session
) -> None:
    assert client.get("/onboarding", follow_redirects=False).headers["location"] == "/login"
    user = add_user(db_session, "surgeon@example.com")
    client.post("/auth", data={"t": magic_links.issue(db_session, user, datetime.now(UTC))})
    assert client.get("/onboarding").status_code == 200
    client.post("/logout")
    assert client.get("/onboarding", follow_redirects=False).status_code == 303


def test_tampered_or_deleted_user_session_is_anonymous(
    client: TestClient, db_session: Session
) -> None:
    client.cookies.set("session", "garbage")
    assert client.get("/onboarding", follow_redirects=False).status_code == 303
    user = add_user(db_session, "surgeon@example.com")
    client.post("/auth", data={"t": magic_links.issue(db_session, user, datetime.now(UTC))})
    db_session.delete(user)
    db_session.commit()
    assert client.get("/onboarding", follow_redirects=False).status_code == 303


def test_add_user_normalises_and_updates(db_session: Session) -> None:
    a = add_user(db_session, " Surgeon@Example.com ", name="Ana")
    b = add_user(db_session, "surgeon@example.com", is_admin=True)
    c = add_user(db_session, "surgeon@example.com", can_calibrate=True)
    assert a.id == b.id == c.id and c.email == "surgeon@example.com"
    assert c.name == "Ana" and c.is_admin and c.can_calibrate  # flags are only granted
    with pytest.raises(ValueError):
        add_user(db_session, "not-an-email")


def test_session_cookie_roundtrip() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    response = Response()
    sessions.start_session(SETTINGS, response, user)  # type: ignore[arg-type]
    raw = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    scope = {"type": "http", "headers": [(b"cookie", f"session={raw}".encode())]}
    assert sessions.session_user_id(SETTINGS, Request(scope)) == user.id
    other = Settings(_env_file=None, secret_key="other")  # type: ignore[call-arg]
    assert sessions.session_user_id(other, Request(scope)) is None
