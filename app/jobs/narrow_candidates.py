"""Weekly ingest, step 3: pick which new papers to grade (SPEC.md §6.3).

Idempotent: re-running in the same week overwrites that week's candidate rows.
"""

from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Candidate, Paper, PaperEmbedding, ProfileVector, SeedPaper, Topic
from app.domain.narrowing import narrow_scores, select_for_grading
from app.embeddings.base import Embedder
from app.jobs.grade_papers import currently_graded

ANCHOR_PATH = Path(__file__).parents[1] / "sources" / "specialty_anchor.txt"


@dataclass
class NarrowStats:
    candidates: int = 0
    selected: int = 0
    missing_embeddings: int = 0


def week_of(day: date) -> date:
    """Monday of the ISO week containing `day`."""
    return day - timedelta(days=day.weekday())


def load_anchor(path: Path = ANCHOR_PATH) -> str:
    return " ".join(path.read_text().split())


@dataclass(frozen=True)
class UserReferences:
    vectors: list[list[float]]  # profile vectors and active topic embeddings
    seeds: frozenset[str]  # every user's seed papers


def user_references(session: Session, model: str) -> UserReferences:
    """What users add to narrowing: their profile vectors, each active topic (so a niche
    topic is not diluted by the rest of a profile), and their seed papers.
    """
    profiles = session.scalars(select(ProfileVector.vector).where(ProfileVector.model == model))
    topics = session.scalars(
        select(Topic.embedding).where(Topic.active, Topic.embedding_model == model)
    )
    vectors = [list(v) for v in [*profiles, *topics] if v is not None]
    return UserReferences(vectors, frozenset(session.scalars(select(SeedPaper.pmid))))


def narrow(
    session: Session,
    embedder: Embedder,
    *,
    since: date,
    week: date,
    limit: int,
    anchor_text: str,
    profile_vectors: Sequence[Sequence[float]] = (),
    always_include: AbstractSet[str] = frozenset(),
) -> NarrowStats:
    """Score papers not yet considered in an earlier week and mark the top `limit` for grading.

    The pool is every paper with an entrez date on or after `since` (the start of the
    active window) that has no candidate row from another week. Using "not yet scored"
    rather than a date range means papers that reach PubMed or our database late are
    still considered once; re-running in the same week re-scores that week's pool.

    References are the specialty anchor plus users' profile and topic vectors
    (`user_references`); `always_include` holds users' seed papers.
    """
    earlier_weeks = select(Candidate.pmid).where(Candidate.week_of != week)
    pool = Paper.entrez_date >= since, Paper.pmid.not_in(earlier_weeks)
    rows = session.execute(
        select(PaperEmbedding.pmid, PaperEmbedding.vector)
        .join(Paper, Paper.pmid == PaperEmbedding.pmid)
        .where(*pool, PaperEmbedding.model == embedder.model)
    ).all()
    total = session.scalar(select(func.count()).select_from(Paper).where(*pool))
    stats = NarrowStats(missing_embeddings=(total or 0) - len(rows))
    if not rows:
        return stats

    anchor = embedder.embed([anchor_text], "query").vectors[0]
    scores = narrow_scores({pmid: list(vec) for pmid, vec in rows}, [anchor, *profile_vectors])
    selected = select_for_grading(scores, limit, always_include)
    stmt = insert(Candidate).values(
        [
            {
                "pmid": pmid,
                "week_of": week,
                "narrow_score": s,
                "selected_for_grading": pmid in selected,
            }
            for pmid, s in scores.items()
        ]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Candidate.pmid, Candidate.week_of],
        set_={
            "narrow_score": stmt.excluded.narrow_score,
            "selected_for_grading": stmt.excluded.selected_for_grading,
        },
    )
    session.execute(stmt)
    session.commit()
    stats.candidates = len(scores)
    stats.selected = len(selected)
    return stats


def selected_ungraded(session: Session, limit: int | None = None) -> list[str]:
    """Papers selected for grading in any week that lack a current-version grade, best
    narrowing score first (the order the spend guard keeps them in)."""
    stmt = (
        select(Candidate.pmid)
        .where(Candidate.selected_for_grading, Candidate.pmid.not_in(currently_graded()))
        .group_by(Candidate.pmid)
        .order_by(func.max(Candidate.narrow_score).desc(), Candidate.pmid.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))
