"""What a user sees: the ranked feed, one paper, the library and history (SPEC.md §8, §11).

Loads rows, hands them to the pure ranking in app.domain.ranking, and pairs the
results back with their papers and grades for display.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Grade, Paper, PaperEmbedding, ProfileVector, Topic
from app.domain.criteria import INTRINSIC_CRITERIA
from app.domain.ranking import (
    GradedPaper,
    PaperState,
    RankedPaper,
    RankingRules,
    pertinence_cosines,
    rank,
    score_paper,
)
from app.feed.states import Tracked, paper_states
from app.grading.rubric import RUBRIC_VERSION
from app.profiles.service import load_preferences

FEED_SIZE = 10


@dataclass(frozen=True)
class FeedItem:
    paper: Paper
    grade: Grade
    ranked: RankedPaper

    @property
    def pmid(self) -> str:
        return self.paper.pmid

    @property
    def state(self) -> PaperState:
        return self.ranked.paper.state


@dataclass(frozen=True)
class Entry:
    """A paper in the library or history; its grade may be missing or outdated."""

    paper: Paper
    state: PaperState
    grade: Grade | None

    @property
    def pmid(self) -> str:
        return self.paper.pmid


def current_grade(session: Session, pmid: str) -> Grade | None:
    """The latest grade under the current rubric version."""
    return session.scalar(
        select(Grade)
        .where(Grade.pmid == pmid, Grade.rubric_version == RUBRIC_VERSION)
        .order_by(Grade.created_at.desc())
        .limit(1)
    )


def _graded_rows(session: Session, *where: ColumnElement[bool]) -> list[tuple[Paper, Grade]]:
    stmt = (
        select(Paper, Grade)
        .join(Grade, Grade.pmid == Paper.pmid)
        .where(Grade.rubric_version == RUBRIC_VERSION, *where)
        .order_by(Grade.pmid, Grade.created_at.desc())
        .ext(distinct_on(Grade.pmid))
    )
    return [(p, g) for p, g in session.execute(stmt)]


def _cosines(
    session: Session, user_id: uuid.UUID, pmids: Sequence[str], model: str
) -> dict[str, float]:
    """Pertinence cosine per paper; empty when the user has no profile vector yet."""
    profile = session.scalar(
        select(ProfileVector.vector).where(
            ProfileVector.user_id == user_id, ProfileVector.model == model
        )
    )
    if profile is None or not pmids:
        return {}
    topics = session.scalars(
        select(Topic.embedding).where(
            Topic.user_id == user_id, Topic.active, Topic.embedding_model == model
        )
    )
    vectors = session.execute(
        select(PaperEmbedding.pmid, PaperEmbedding.vector).where(
            PaperEmbedding.pmid.in_(pmids), PaperEmbedding.model == model
        )
    )
    return pertinence_cosines(
        {pmid: list(v) for pmid, v in vectors},
        profile=list(profile),
        topics=[list(t) for t in topics if t is not None],
    )


def _score(
    session: Session, user_id: uuid.UUID, settings: Settings, rows: list[tuple[Paper, Grade]]
) -> tuple[RankingRules, dict[str, GradedPaper]]:
    states = paper_states(session, user_id)
    cos = _cosines(session, user_id, [p.pmid for p, _ in rows], settings.embedding_model)
    rules = RankingRules(
        preferences=load_preferences(session, user_id),
        gate=settings.pertinence_gate,
        thresholds=settings.pertinence_thresholds,
    )
    graded = {
        p.pmid: GradedPaper(
            pmid=p.pmid,
            scores={c: getattr(g, c) for c in INTRINSIC_CRITERIA},
            pertinence_cos=cos.get(p.pmid, 0.0),
            entrez_date=p.entrez_date,
            pub_types=tuple(p.pub_types),
            state=states[p.pmid].state if p.pmid in states else PaperState(),
        )
        for p, g in rows
    }
    return rules, graded


def feed(
    session: Session, user_id: uuid.UUID, settings: Settings, today: date, limit: int = FEED_SIZE
) -> list[FeedItem]:
    """Top eligible papers of the active window, best first."""
    since = today - timedelta(days=settings.active_window_days)
    rows = _graded_rows(session, Paper.entrez_date >= since)
    rules, graded = _score(session, user_id, settings, rows)
    by_pmid = {p.pmid: (p, g) for p, g in rows}
    return [FeedItem(*by_pmid[r.paper.pmid], r) for r in rank(graded.values(), rules)[:limit]]


def paper(session: Session, user_id: uuid.UUID, pmid: str, settings: Settings) -> FeedItem | None:
    """One graded paper with its scores for this user, eligible or not."""
    rows = _graded_rows(session, Paper.pmid == pmid)
    if not rows:
        return None
    rules, graded = _score(session, user_id, settings, rows)
    p, g = rows[0]
    return FeedItem(p, g, score_paper(graded[pmid], rules))


def _entries(session: Session, tracked: dict[str, Tracked]) -> list[Entry]:
    """Papers for `tracked`, most recent feedback first."""
    if not tracked:
        return []
    papers = {p.pmid: p for p in session.scalars(select(Paper).where(Paper.pmid.in_(tracked)))}
    grades = {g.pmid: g for _, g in _graded_rows(session, Paper.pmid.in_(tracked))}
    order = sorted(tracked, key=lambda pmid: tracked[pmid].last_event_at, reverse=True)
    return [Entry(papers[p], tracked[p].state, grades.get(p)) for p in order if p in papers]


def library(session: Session, user_id: uuid.UUID) -> list[Entry]:
    """Liked papers."""
    states = paper_states(session, user_id)
    return _entries(session, {p: t for p, t in states.items() if t.state.liked})


def history(session: Session, user_id: uuid.UUID) -> list[Entry]:
    """Read or dismissed papers, which the feed hides; each can be undone."""
    states = paper_states(session, user_id)
    hidden = {p: t for p, t in states.items() if t.state.read or t.state.dismissed}
    return _entries(session, hidden)
