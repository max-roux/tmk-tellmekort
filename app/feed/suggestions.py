"""Weight suggestions from a user's likes (SPEC.md §8.5): find, apply, dismiss."""

import uuid

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import CriterionSettings
from app.domain.suggestions import raised_weight, suggest_weight
from app.feed.queries import scores
from app.feed.states import emailed_pmids, paper_states
from app.profiles.service import load_preferences


def current_suggestion(session: Session, user_id: uuid.UUID, settings: Settings) -> str | None:
    """The criterion to suggest raising, comparing liked papers with papers shown to the
    user (emailed, or given any feedback) that they did not like."""
    states = paper_states(session, user_id)
    liked = {p for p, t in states.items() if t.state.liked}
    shown = set(states) | emailed_pmids(session, user_id)
    scored = scores(session, user_id, settings, sorted(shown))
    return suggest_weight(
        [s for p, s in scored.items() if p in liked],
        [s for p, s in scored.items() if p not in liked],
        load_preferences(session, user_id).weights,
        dismissed=_dismissed(session, user_id),
    )


def _dismissed(session: Session, user_id: uuid.UUID) -> frozenset[str]:
    row = session.get(CriterionSettings, user_id)
    return frozenset(row.dismissed_suggestions) if row else frozenset()


def apply(session: Session, user_id: uuid.UUID, criterion: str) -> None:
    """Raise `criterion` to one above the highest weight (at most 5). Commits."""
    row = session.get(CriterionSettings, user_id)
    if row is None:
        raise LookupError("no saved weights")
    setattr(row, f"w_{criterion}", raised_weight(load_preferences(session, user_id).weights))
    session.commit()


def dismiss(session: Session, user_id: uuid.UUID, criterion: str) -> None:
    """Never suggest `criterion` again. Commits."""
    row = session.get(CriterionSettings, user_id)
    if row is None:
        raise LookupError("no saved weights")
    if criterion not in row.dismissed_suggestions:
        row.dismissed_suggestions = [*row.dismissed_suggestions, criterion]
    session.commit()
