"""SMTP client, e.g. a Gmail account with an app password: free, no domain needed (SPEC.md §3).

Port 587 upgrades with STARTTLS; port 465 is TLS from the start. One connection per message:
the pilot sends a handful a week.
"""

import smtplib
from collections.abc import Callable
from email.message import EmailMessage as MimeMessage
from email.utils import make_msgid
from typing import Any

from app.email.base import EmailMessage, MailerError, sender_with_name

IMPLICIT_TLS_PORT = 465


class SmtpMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        smtp: Callable[..., Any] = smtplib.SMTP,
        smtp_ssl: Callable[..., Any] = smtplib.SMTP_SSL,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender_with_name(sender)
        self._connect = smtp_ssl if port == IMPLICIT_TLS_PORT else smtp

    def _mime(self, message: EmailMessage) -> MimeMessage:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime["Message-ID"] = make_msgid(domain=self._sender.rsplit("@", 1)[-1].rstrip(">"))
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")
        return mime

    def send(self, message: EmailMessage) -> str:
        mime = self._mime(message)
        try:
            with self._connect(self._host, self._port, timeout=30) as conn:
                if self._port != IMPLICIT_TLS_PORT:
                    conn.starttls()
                conn.login(self._username, self._password)
                conn.send_message(mime)
        except (smtplib.SMTPException, OSError) as e:
            # Type and reply code only: the server's text can name the recipient, and these
            # errors are logged (no personal data in logs).
            code = getattr(e, "smtp_code", None) or getattr(e, "errno", None)
            raise MailerError(f"smtp: {type(e).__name__}" + (f" {code}" if code else "")) from e
        return str(mime["Message-ID"])
