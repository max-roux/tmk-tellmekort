"""Magic-link sign-in (SPEC.md §3, §16): random, single-use, 15-minute tokens.

Only a SHA-256 of each token is stored. Rate limit: 5 requests per hour per email, and
50 per hour across all emails (a ceiling on the sign-in email we can be made to send).
There is no per-IP limit: behind Render's proxy the client address is not trustworthy.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.models import LoginAttempt, MagicLink, User

LINK_TTL = timedelta(minutes=15)
RATE_WINDOW = timedelta(hours=1)
RATE_LIMIT = 5
GLOBAL_RATE_LIMIT = 50


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(session: Session, user: User, now: datetime) -> str:
    """A new sign-in token for `user`, pruning long-expired ones. Commits."""
    token = secrets.token_urlsafe(32)
    session.execute(delete(MagicLink).where(MagicLink.expires_at < now - timedelta(days=1)))
    session.add(MagicLink(token_hash=hash_token(token), user_id=user.id, expires_at=now + LINK_TTL))
    session.commit()
    return token


def consume(session: Session, token: str, now: datetime) -> User | None:
    """The user for an unused, unexpired token, marking it used. None otherwise. Commits.

    The update is conditional on `used_at IS NULL`, so two concurrent requests with the
    same token cannot both succeed.
    """
    user_id = session.scalar(
        update(MagicLink)
        .where(
            MagicLink.token_hash == hash_token(token),
            MagicLink.used_at.is_(None),
            MagicLink.expires_at > now,
        )
        .values(used_at=now)
        .returning(MagicLink.user_id)
    )
    session.commit()
    return session.get(User, user_id) if user_id else None


def allow_attempt(session: Session, email: str, now: datetime) -> bool:
    """Record a /login request; False when the email or everyone is over the limit. Commits.

    Attempts older than the window are pruned. Over-limit requests are not recorded, so
    a blocked client is let back in once its earlier requests age out of the window.
    """
    since = now - RATE_WINDOW
    session.execute(delete(LoginAttempt).where(LoginAttempt.created_at <= since))
    recent = select(func.count()).select_from(LoginAttempt).where(LoginAttempt.created_at > since)
    by_email = session.scalar(recent.where(LoginAttempt.email == email)) or 0
    total = session.scalar(recent) or 0
    if by_email >= RATE_LIMIT or total >= GLOBAL_RATE_LIMIT:
        session.commit()
        return False
    session.add(LoginAttempt(email=email, created_at=now))
    session.commit()
    return True
