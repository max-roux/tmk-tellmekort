"""Postmark transactional client (POST /email). No open or click tracking (SPEC.md §10.5)."""

import httpx
from pydantic import BaseModel, ValidationError

from app.email.base import EmailMessage, MailerError, sender_with_name

POSTMARK_BASE = "https://api.postmarkapp.com"


class _Response(BaseModel):
    ErrorCode: int
    Message: str
    MessageID: str = ""


class PostmarkMailer:
    def __init__(
        self,
        *,
        server_token: str,
        sender: str,
        stream: str = "outbound",
        http: httpx.Client | None = None,
    ) -> None:
        self._sender = sender_with_name(sender)
        self._stream = stream
        self._http = http or httpx.Client(base_url=POSTMARK_BASE, timeout=30)
        self._headers = {"Accept": "application/json", "X-Postmark-Server-Token": server_token}

    def close(self) -> None:
        self._http.close()

    def send(self, message: EmailMessage) -> str:
        payload = {
            "From": self._sender,
            "To": message.to,
            "Subject": message.subject,
            "TextBody": message.text,
            "HtmlBody": message.html,
            "MessageStream": self._stream,
            "TrackOpens": False,
            "TrackLinks": "None",
        }
        try:
            resp = self._http.post("/email", json=payload, headers=self._headers)
        except httpx.TransportError as e:
            raise MailerError(f"postmark: {e}") from e
        try:
            body = _Response.model_validate_json(resp.content)
        except ValidationError:
            raise MailerError(f"postmark: HTTP {resp.status_code}") from None
        if resp.is_error or body.ErrorCode != 0:
            # Postmark's message names the problem (bad sender, inactive recipient...).
            raise MailerError(f"postmark: error {body.ErrorCode}: {body.Message}")
        return body.MessageID
