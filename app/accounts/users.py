"""User accounts. No self-serve sign-up (SPEC.md §1): the operator adds users."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CriterionSettings, LoginAttempt, User


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == normalise_email(email)))


def add_user(
    session: Session,
    email: str,
    *,
    name: str = "",
    is_admin: bool = False,
    can_calibrate: bool = False,
) -> User:
    """Create the user, or update name and grant flags if the email exists. Commits.

    Flags are only ever granted here, never revoked.
    """
    email = normalise_email(email)
    if "@" not in email:
        raise ValueError(f"not an email address: {email!r}")
    user = get_by_email(session, email)
    if user is None:
        user = User(email=email, name=name, is_admin=is_admin, can_calibrate=can_calibrate)
        session.add(user)
    else:
        user.name = name or user.name
        user.is_admin = is_admin or user.is_admin
        user.can_calibrate = can_calibrate or user.can_calibrate
    session.commit()
    return user


def is_onboarded(session: Session, user: User) -> bool:
    """Onboarding ends by saving criterion settings (SPEC.md §11 step 4)."""
    return session.get(CriterionSettings, user.id) is not None


def delete_user(session: Session, user: User) -> None:
    """Remove the user and every row about them (SPEC.md §16). Commits.

    Their topics, seeds, settings, profile, feedback, disputes, sends and sign-in links go
    by cascade; login attempts hold only the email, so they are deleted by it. Papers and
    grades are shared and stay.
    """
    session.execute(delete(LoginAttempt).where(LoginAttempt.email == user.email))
    session.delete(user)
    session.commit()
