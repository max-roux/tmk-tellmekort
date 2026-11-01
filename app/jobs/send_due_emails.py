"""Hourly job: send each due user their weekly email (SPEC.md §10).

Idempotent: a user's email for a week is claimed by inserting its `email_sends` row,
unique per user and week, before sending; a failed send deletes the claim so the next
run retries.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.accounts.users import is_onboarded
from app.config import Settings
from app.db.models import EmailSend, User
from app.domain.criteria import INTRINSIC_CRITERIA
from app.domain.picks import Picks, is_due, local_week, select_picks
from app.email.actions import ACTIONS, action_link
from app.email.alerts import alert_admin
from app.email.base import NAME, EmailMessage, Mailer, MailerError, render
from app.feed import queries
from app.feed.queries import FeedItem
from app.feed.states import emailed_pmids
from app.grading.rubric import criterion_labels
from app.profiles.service import load_preferences

log = logging.getLogger(__name__)

FRESH_DAYS = 7


@dataclass
class SendStats:
    sent: int = 0
    quiet: int = 0
    failed: int = 0


@dataclass(frozen=True)
class EmailPaper:
    """One paper as the email shows it."""

    label: str  # "Fresh this week" | "You may have missed"
    item: FeedItem
    reasons: list[tuple[str, str]]  # (criterion name, justification), top 2 by weight
    links: dict[str, str]  # action -> one-tap link


def due_users(session: Session, now: datetime) -> list[User]:
    """Onboarded users whose weekly slot has passed and who have no email this week."""
    due = []
    for user in session.scalars(select(User).order_by(User.created_at)):
        tz = ZoneInfo(user.timezone)
        if not is_due(now, tz, weekday=user.send_weekday, at=user.send_local_time):
            continue
        sent = session.scalar(
            select(EmailSend.id).where(
                EmailSend.user_id == user.id, EmailSend.week_of == local_week(now, tz)
            )
        )
        if sent is None and is_onboarded(session, user):
            due.append(user)
    return due


def _top_reasons(item: FeedItem, weights: dict[str, float]) -> list[tuple[str, str]]:
    """Justifications of the two intrinsic criteria the user weights most."""
    names = dict(criterion_labels())
    top = sorted(INTRINSIC_CRITERIA, key=lambda c: -weights[c])[:2]
    return [(names[c], item.grade.justifications[c]) for c in top]


def _email_papers(
    picks: Picks,
    items: dict[str, FeedItem],
    weights: dict[str, float],
    user: User,
    send_id: uuid.UUID,
    settings: Settings,
) -> list[EmailPaper]:
    slots = [("Fresh this week", picks.fresh), ("You may have missed", picks.missed)]
    return [
        EmailPaper(
            label,
            items[r.paper.pmid],
            _top_reasons(items[r.paper.pmid], weights),
            {a: action_link(settings, user.id, r.paper.pmid, a, send_id) for a in ACTIONS},
        )
        for label, r in slots
        if r is not None
    ]


def _pick(
    session: Session, user: User, settings: Settings, now: datetime
) -> tuple[Picks, dict[str, FeedItem]]:
    ranked = queries.feed(session, user.id, settings, now.date(), limit=None)
    picks = select_picks(
        [i.ranked for i in ranked],
        sent=emailed_pmids(session, user.id),
        fresh_since=now.date() - timedelta(days=FRESH_DAYS),
        cutoff=settings.email_min_weighted,
    )
    return picks, {i.pmid: i for i in ranked}


def _claim(session: Session, user: User, now: datetime) -> uuid.UUID | None:
    """Insert this week's send row; None if another run already has it."""
    week = local_week(now, ZoneInfo(user.timezone))
    stmt = insert(EmailSend).values(id=uuid.uuid4(), user_id=user.id, week_of=week, sent_at=now)
    send_id = session.execute(stmt.on_conflict_do_nothing().returning(EmailSend.id)).scalar()
    session.commit()
    return send_id


def _message(
    session: Session, user: User, settings: Settings, now: datetime, send_id: uuid.UUID
) -> tuple[EmailMessage, Picks]:
    picks, items = _pick(session, user, settings, now)
    base = settings.base_url.rstrip("/")
    if picks.quiet:
        subject = f"{NAME}: a quiet week"
        return render("weekly_quiet", subject, user.email, user=user, base=base), picks
    papers = _email_papers(
        picks, items, load_preferences(session, user.id).weights, user, send_id, settings
    )
    subject = f"{NAME}: {papers[0].item.paper.title}"
    if len(subject) > 90:
        subject = subject[:87].rsplit(" ", 1)[0] + "…"
    message = render(
        "weekly",
        subject,
        user.email,
        user=user,
        base=base,
        papers=papers,
        criteria=criterion_labels(),
    )
    return message, picks


def preview(session: Session, user: User, settings: Settings, now: datetime) -> EmailMessage:
    """The email `user` would get now, without recording a send (its buttons won't work)."""
    message, _ = _message(session, user, settings, now, uuid.uuid4())
    return message


def send_weekly(
    session: Session, user: User, settings: Settings, mailer: Mailer, now: datetime
) -> Picks | None:
    """Claim, build and send one user's email. None if not sent (claimed elsewhere or failed)."""
    send_id = _claim(session, user, now)
    if send_id is None:
        return None
    try:
        message, picks = _message(session, user, settings, now, send_id)
        message_id = mailer.send(message)
    except Exception as e:
        # Release the claim so the next hourly run retries; re-raise anything unexpected.
        session.rollback()
        session.execute(delete(EmailSend).where(EmailSend.id == send_id))
        session.commit()
        if not isinstance(e, MailerError):
            raise
        log.error("weekly email to user %s failed, will retry: %s", user.id, e)
        return None
    send = session.get(EmailSend, send_id)
    assert send is not None
    send.postmark_message_id = message_id
    send.fresh_pmid = picks.fresh.paper.pmid if picks.fresh else None
    send.missed_pmid = picks.missed.paper.pmid if picks.missed else None
    session.commit()
    if picks.quiet:
        alert_admin(
            mailer,
            settings,
            "Quiet week for a user",
            f"Quiet week: nothing was eligible for {user.email}.\n"
            "Their profile or the specialty query needs attention.",
        )
    return picks


def send_due(session: Session, settings: Settings, mailer: Mailer, now: datetime) -> SendStats:
    stats = SendStats()
    for user in due_users(session, now):
        picks = send_weekly(session, user, settings, mailer, now)
        if picks is None:
            stats.failed += 1
            continue
        stats.sent += 1
        stats.quiet += picks.quiet
    return stats
