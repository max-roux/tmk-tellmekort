"""User accounts. No self-serve sign-up (SPEC.md §1): the operator adds users."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CriterionSettings, User


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == normalise_email(email)))


def add_user(session: Session, email: str, *, name: str = "", is_admin: bool = False) -> User:
    """Create the user, or update name and admin flag if the email exists. Commits."""
    email = normalise_email(email)
    if "@" not in email:
        raise ValueError(f"not an email address: {email!r}")
    user = get_by_email(session, email)
    if user is None:
        user = User(email=email, name=name, is_admin=is_admin)
        session.add(user)
    else:
        user.name = name or user.name
        user.is_admin = is_admin or user.is_admin
    session.commit()
    return user


def is_onboarded(session: Session, user: User) -> bool:
    """Onboarding ends by saving criterion settings (SPEC.md §11 step 4)."""
    return session.get(CriterionSettings, user.id) is not None
