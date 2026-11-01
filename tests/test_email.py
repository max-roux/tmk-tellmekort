import email.message
import json
import smtplib
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

import httpx
import pytest

from app.email.base import EmailMessage, MailerError, render, sender_with_name
from app.email.outbox import OutboxMailer
from app.email.postmark import POSTMARK_BASE, PostmarkMailer
from app.email.smtp import SmtpMailer

LINK = "https://maxfac.test/auth#tok-123"


def message() -> EmailMessage:
    return render("magic_link", "Sign in", "surgeon@example.com", link=LINK, minutes=15)


def mailer(handler: Callable[[httpx.Request], httpx.Response]) -> PostmarkMailer:
    http = httpx.Client(base_url=POSTMARK_BASE, transport=httpx.MockTransport(handler))
    return PostmarkMailer(server_token="pm-test", sender="papers@mail.example.com", http=http)


def test_magic_link_template_has_link_in_both_parts() -> None:
    m = message()
    assert LINK in m.text and LINK in m.html
    assert "15 minutes" in m.text


def test_postmark_request_shape_without_tracking() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "To": "x",
                "SubmittedAt": "now",
                "MessageID": "pm-1",
                "ErrorCode": 0,
                "Message": "OK",
            },
        )

    assert mailer(handler).send(message()) == "pm-1"
    req = seen[0]
    assert req.url.path == "/email"
    assert req.headers["X-Postmark-Server-Token"] == "pm-test"
    body = json.loads(req.content)
    assert body["From"] == "Tell Me Kort <papers@mail.example.com>"
    assert body["To"] == "surgeon@example.com"
    assert body["MessageStream"] == "outbound"
    assert body["TrackOpens"] is False and body["TrackLinks"] == "None"
    assert LINK in body["TextBody"] and LINK in body["HtmlBody"]


def test_sender_keeps_a_display_name_it_already_has() -> None:
    assert sender_with_name("papers@mail.example.com") == "Tell Me Kort <papers@mail.example.com>"
    assert sender_with_name("TMK <papers@mail.example.com>") == "TMK <papers@mail.example.com>"


def test_postmark_errors_raise() -> None:
    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"ErrorCode": 406, "Message": "Inactive recipient"})

    with pytest.raises(MailerError, match="406"):
        mailer(rejected).send(message())

    def garbage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(MailerError, match="502"):
        mailer(garbage).send(message())


def test_outbox_writes_text_and_html(tmp_path: Path) -> None:
    message_id = OutboxMailer(tmp_path).send(message())
    assert message_id.startswith("outbox-")
    txt = next(tmp_path.glob("*.txt")).read_text()
    assert "To: surgeon@example.com" in txt and LINK in txt
    assert len(list(tmp_path.glob("*.html"))) == 1


class FakeSmtp:
    """Stands in for smtplib.SMTP / SMTP_SSL; records the conversation."""

    instances: ClassVar[list["FakeSmtp"]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.address = (host, port)
        self.calls: list[str] = []
        self.sent: list[email.message.EmailMessage] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        if password != "app-pass":
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        self.calls.append(f"login {user}")

    def send_message(self, msg: email.message.EmailMessage) -> None:
        self.calls.append("send")
        self.sent.append(msg)


def smtp_mailer(port: int = 587, password: str = "app-pass") -> SmtpMailer:
    FakeSmtp.instances.clear()
    return SmtpMailer(
        host="smtp.gmail.com",
        port=port,
        username="maxfacpapers@gmail.com",
        password=password,
        sender="maxfacpapers@gmail.com",
        smtp=FakeSmtp,
        smtp_ssl=FakeSmtp,
    )


def test_smtp_sends_text_and_html_over_starttls() -> None:
    message_id = smtp_mailer().send(message())
    conn = FakeSmtp.instances[0]
    assert conn.address == ("smtp.gmail.com", 587)
    assert conn.calls == ["starttls", "login maxfacpapers@gmail.com", "send", "quit"]
    sent = conn.sent[0]
    assert sent["From"] == "Tell Me Kort <maxfacpapers@gmail.com>"
    assert sent["To"] == "surgeon@example.com"
    assert sent["Subject"] == "Sign in"
    assert sent["Message-ID"] == message_id
    text = sent.get_body(("plain",))
    html = sent.get_body(("html",))
    assert text is not None and LINK in text.get_content()
    assert html is not None and LINK in html.get_content()


def test_smtp_port_465_uses_implicit_tls() -> None:
    smtp_mailer(port=465).send(message())
    assert FakeSmtp.instances[0].calls[0] == "login maxfacpapers@gmail.com"


def test_smtp_errors_raise_without_the_password() -> None:
    with pytest.raises(MailerError, match="smtp") as err:
        smtp_mailer(password="wrong").send(message())
    assert "wrong" not in str(err.value)
