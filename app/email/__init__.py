"""Outgoing email. `mailer_for` picks the mailer for the web app and the jobs alike."""

import logging
from functools import lru_cache

from app.config import Settings
from app.email.base import Mailer
from app.email.outbox import OutboxMailer
from app.email.postmark import PostmarkMailer

log = logging.getLogger(__name__)


@lru_cache
def _postmark(server_token: str, sender: str) -> PostmarkMailer:
    # One long-lived client: it must outlive the request, since sign-in emails are sent
    # from a background task after the response.
    return PostmarkMailer(server_token=server_token, sender=sender)


def mailer_for(settings: Settings) -> Mailer:
    """Postmark when configured; otherwise the local outbox folder (development)."""
    if not settings.postmark_server_token:
        log.warning("POSTMARK_SERVER_TOKEN not set: writing email to the local outbox")
        return OutboxMailer()
    return _postmark(settings.postmark_server_token, settings.email_from)
