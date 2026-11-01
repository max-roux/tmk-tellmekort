"""Recording feedback events and score disputes (SPEC.md §9)."""

import uuid

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import FEEDBACK_KINDS, Feedback, ScoreDispute
from app.domain.criteria import ALL_CRITERIA
from app.feed.queries import current_grade
from app.profiles.service import coefficients, refresh_profile_vector

# Likes and dismissals feed the profile vector (§8.1); reads do not.
_RESHAPES_PROFILE = {"like", "unlike", "not_for_me", "undismiss"}


def record(
    session: Session, user_id: uuid.UUID, pmid: str, kind: str, source: str, settings: Settings
) -> None:
    """Append one event and refresh the profile vector when it changes. Commits."""
    if kind not in FEEDBACK_KINDS:
        raise ValueError(f"unknown feedback kind {kind!r}")
    session.add(Feedback(user_id=user_id, pmid=pmid, kind=kind, source=source))
    session.commit()
    if kind in _RESHAPES_PROFILE:
        refresh_profile_vector(session, user_id, settings.embedding_model, coefficients(settings))


def dispute(
    session: Session,
    user_id: uuid.UUID,
    pmid: str,
    criterion: str,
    user_score: int | None,
    comment: str,
) -> None:
    """Record disagreement with one score of the current grade. Commits.

    Raises ValueError for an unknown criterion or score, LookupError when ungraded.
    """
    if criterion not in ALL_CRITERIA:
        raise ValueError(f"unknown criterion {criterion!r}")
    if user_score is not None and not 1 <= user_score <= 5:
        raise ValueError("score must be 1-5")
    grade = current_grade(session, pmid)
    if grade is None:
        raise LookupError(f"no current grade for {pmid}")
    session.add(
        ScoreDispute(
            user_id=user_id,
            pmid=pmid,
            grade_id=grade.id,
            criterion=criterion,
            user_score=user_score,
            comment=comment.strip(),
        )
    )
    session.commit()
