"""Outgoing email. `mailer_for` picks the mailer for the web app and the jobs alike."""

import logging
from functools import lru_cache

from app.config import Settings
from app.email.base import Mailer
from app.email.outbox import OutboxMailer
from app.email.postmark import PostmarkMailer
from app.email.smtp import SmtpMailer

log = logging.getLogger(__name__)


@lru_cache
def _postmark(server_token: str, sender: str) -> PostmarkMailer:
    # One long-lived client: it must outlive the request, since sign-in emails are sent
    # from a background task after the response.
    return PostmarkMailer(server_token=server_token, sender=sender)


def mailer_for(settings: Settings) -> Mailer:
    """Postmark when configured, else SMTP, else the local outbox folder (development)."""
    if settings.postmark_server_token:
        return _postmark(settings.postmark_server_token, settings.email_from)
    if settings.smtp_host:
        return SmtpMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            sender=settings.email_from,
        )
    log.warning("No POSTMARK_SERVER_TOKEN or SMTP_HOST: writing email to the local outbox")
    return OutboxMailer()
