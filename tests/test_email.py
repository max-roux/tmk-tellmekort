import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.email.base import EmailMessage, MailerError, render, sender_with_name
from app.email.outbox import OutboxMailer
from app.email.postmark import POSTMARK_BASE, PostmarkMailer

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
