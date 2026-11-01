"""Per-user paper states, derived from the append-only feedback log (SPEC.md §9)."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Feedback
from app.domain.ranking import PaperState, derive_state


@dataclass(frozen=True)
class Tracked:
    state: PaperState
    last_event_at: datetime


def paper_states(session: Session, user_id: uuid.UUID) -> dict[str, Tracked]:
    """State of every paper the user has given feedback on."""
    events: dict[str, list[str]] = defaultdict(list)
    last: dict[str, datetime] = {}
    rows = session.execute(
        select(Feedback.pmid, Feedback.kind, Feedback.created_at)
        .where(Feedback.user_id == user_id)
        .order_by(Feedback.created_at, Feedback.id)
    )
    for pmid, kind, at in rows:
        events[pmid].append(kind)
        last[pmid] = at
    return {pmid: Tracked(derive_state(kinds), last[pmid]) for pmid, kinds in events.items()}
