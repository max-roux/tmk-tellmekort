"""Alerts to the operator (ADMIN_EMAIL): quiet weeks, the spend cap, failed runs."""

import logging

from app.config import Settings
from app.email.base import Mailer, MailerError, render

log = logging.getLogger(__name__)


def alert_admin(mailer: Mailer, settings: Settings, subject: str, body: str) -> None:
    """Best effort: an alert that cannot be sent is logged, never raised."""
    if not settings.admin_email:
        log.warning("alert not sent, ADMIN_EMAIL unset: %s", subject)
        return
    try:
        mailer.send(render("admin_alert", f"[Maxfac] {subject}", settings.admin_email, body=body))
    except MailerError as e:
        log.error("alert '%s' failed: %s", subject, e)
