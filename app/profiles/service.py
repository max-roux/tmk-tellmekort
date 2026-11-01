"""Profile changes: topics, seed papers, preferences, and the cached profile vector.

Embedding failures never block a save: topics and seeds are stored without embeddings
and `cli.py embed` fills them in and refreshes profile vectors later.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import CriterionSettings, Paper, PaperEmbedding, ProfileVector, SeedPaper, Topic
from app.domain.criteria import ALL_CRITERIA
from app.domain.preferences import Preferences
from app.domain.ranking import ProfileCoefficients, profile_vector
from app.domain.seeds import SeedRefs
from app.embeddings.base import Embedder, EmbeddingError
from app.feed.states import paper_states
from app.jobs.embed_papers import embed_pmids
from app.jobs.weekly_ingest import store_papers
from app.profiles.topics import ProposedTopic
from app.sources.pubmed import PubMedClient

log = logging.getLogger(__name__)


def coefficients(settings: Settings) -> ProfileCoefficients:
    return ProfileCoefficients(
        topics=settings.profile_coef_topics,
        seeds=settings.profile_coef_seeds,
        liked=settings.profile_coef_liked,
        not_for_me=settings.profile_coef_not_for_me,
    )


# --------------------------------------------------------------------------- topics


def active_topics(session: Session, user_id: uuid.UUID) -> list[Topic]:
    return list(
        session.scalars(
            select(Topic)
            .where(Topic.user_id == user_id, Topic.active)
            .order_by(Topic.created_at, Topic.label)
        )
    )


def replace_topics(
    session: Session, user_id: uuid.UUID, topics: Sequence[ProposedTopic], source: str
) -> None:
    """Make `topics` the user's topic list, keeping embeddings of unchanged descriptions.

    Commits. Embed afterwards with `embed_topics`.
    """
    old = {t.description: t for t in session.scalars(select(Topic).where(Topic.user_id == user_id))}
    session.execute(delete(Topic).where(Topic.user_id == user_id))
    for t in topics:
        kept = old.get(t.description)
        session.add(
            Topic(
                user_id=user_id,
                label=t.label,
                description=t.description,
                source=source,
                embedding=kept.embedding if kept else None,
                embedding_model=kept.embedding_model if kept else None,
            )
        )
    session.commit()


def embed_topics(session: Session, embedder: Embedder, user_id: uuid.UUID | None = None) -> int:
    """Embed topics lacking an embedding from the current model. Commits; returns count."""
    stmt = select(Topic).where(
        or_(Topic.embedding_model.is_(None), Topic.embedding_model != embedder.model)
    )
    if user_id is not None:
        stmt = stmt.where(Topic.user_id == user_id)
    topics = list(session.scalars(stmt))
    if not topics:
        return 0
    vectors = embedder.embed([t.description for t in topics], "query").vectors
    for t, v in zip(topics, vectors, strict=True):
        t.embedding, t.embedding_model = v, embedder.model
    session.commit()
    return len(topics)


# --------------------------------------------------------------------------- seeds


@dataclass
class SeedResult:
    added: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)  # PMIDs/DOIs PubMed did not return
    no_abstract: list[str] = field(default_factory=list)  # found, but nothing to match on


def seed_papers(session: Session, user_id: uuid.UUID) -> list[Paper]:
    return list(
        session.scalars(
            select(Paper)
            .join(SeedPaper, SeedPaper.pmid == Paper.pmid)
            .where(SeedPaper.user_id == user_id)
            .order_by(Paper.entrez_date.desc())
        )
    )


def add_seeds(
    session: Session, user_id: uuid.UUID, refs: SeedRefs, pubmed: PubMedClient
) -> SeedResult:
    """Resolve PMIDs and DOIs through PubMed, store the papers and link them. Commits."""
    result = SeedResult()
    pmids = list(refs.pmids)
    for doi in refs.dois:
        found = pubmed.find(f'"{doi}"[doi]', retmax=1)
        if found:
            pmids.append(found[0])
        else:
            result.not_found.append(doi)
    pmids = list(dict.fromkeys(pmids))
    known = set(session.scalars(select(Paper.pmid).where(Paper.pmid.in_(pmids))))
    if missing := [p for p in pmids if p not in known]:
        fetched = pubmed.fetch(missing)
        store_papers(session, fetched.papers)
        known |= {p.pmid for p in fetched.papers}
        result.no_abstract = [p for p in missing if p in set(fetched.skipped_no_abstract)]
    result.not_found += [p for p in pmids if p not in known and p not in result.no_abstract]
    result.added = [p for p in pmids if p in known]
    if result.added:
        stmt = insert(SeedPaper).values([{"user_id": user_id, "pmid": p} for p in result.added])
        session.execute(stmt.on_conflict_do_nothing())
    session.commit()
    return result


def remove_seed(session: Session, user_id: uuid.UUID, pmid: str) -> None:
    session.execute(delete(SeedPaper).where(SeedPaper.user_id == user_id, SeedPaper.pmid == pmid))
    session.commit()


# --------------------------------------------------------------------------- preferences


def load_preferences(session: Session, user_id: uuid.UUID) -> Preferences:
    """The user's saved preferences, or the defaults (all weights 1, no minimums)."""
    row = session.get(CriterionSettings, user_id) or CriterionSettings(
        **{f"w_{c}": 1.0 for c in ALL_CRITERIA}, hide_case_reports=True
    )
    return Preferences(
        weights={c: getattr(row, f"w_{c}") for c in ALL_CRITERIA},
        minimums={c: getattr(row, f"min_{c}") for c in ALL_CRITERIA},
        hide_case_reports=row.hide_case_reports,
        study_types=frozenset(row.study_types) if row.study_types is not None else None,
    )


def save_preferences(session: Session, user_id: uuid.UUID, prefs: Preferences) -> None:
    values: dict[str, object] = {
        **{f"w_{c}": w for c, w in prefs.weights.items()},
        **{f"min_{c}": m for c, m in prefs.minimums.items()},
        "hide_case_reports": prefs.hide_case_reports,
    }
    stmt = insert(CriterionSettings).values(user_id=user_id, **values)
    session.execute(stmt.on_conflict_do_update(index_elements=["user_id"], set_=values))
    session.commit()


# --------------------------------------------------------------------------- profile vector


def _paper_vectors(session: Session, pmids: list[str], model: str) -> list[list[float]]:
    if not pmids:
        return []
    rows = session.scalars(
        select(PaperEmbedding.vector).where(
            PaperEmbedding.pmid.in_(pmids), PaperEmbedding.model == model
        )
    )
    return [list(v) for v in rows]


def refresh_profile_vector(
    session: Session, user_id: uuid.UUID, model: str, coefs: ProfileCoefficients
) -> bool:
    """Recompute the cached profile vector from embeddings of `model`. Commits.

    Returns False (and drops any cached vector) when nothing is embedded yet.
    """
    states = paper_states(session, user_id)
    liked = [p for p, t in states.items() if t.state.liked]
    dismissed = [p for p, t in states.items() if t.state.dismissed]
    topics = session.scalars(
        select(Topic.embedding).where(
            Topic.user_id == user_id, Topic.active, Topic.embedding_model == model
        )
    )
    seeds = session.scalars(
        select(PaperEmbedding.vector)
        .join(SeedPaper, SeedPaper.pmid == PaperEmbedding.pmid)
        .where(SeedPaper.user_id == user_id, PaperEmbedding.model == model)
    )
    vector = profile_vector(
        topics=[list(v) for v in topics if v is not None],
        seeds=[list(v) for v in seeds],
        liked=_paper_vectors(session, liked, model),
        not_for_me=_paper_vectors(session, dismissed, model),
        coefficients=coefs,
    )
    if vector is None:
        session.execute(delete(ProfileVector).where(ProfileVector.user_id == user_id))
        session.commit()
        return False
    stmt = insert(ProfileVector).values(user_id=user_id, model=model, vector=vector)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={"model": model, "vector": vector, "updated_at": func.now()},
        )
    )
    session.commit()
    return True


def sync_embeddings(
    session: Session,
    embedder: Embedder | None,
    user_id: uuid.UUID,
    coefs: ProfileCoefficients,
) -> bool:
    """Embed the user's topics and seeds, then refresh their profile vector.

    Best effort: returns False when no embedder is configured or the provider fails.
    """
    if embedder is None:
        return False
    try:
        embed_topics(session, embedder, user_id)
        seeds = list(session.scalars(select(SeedPaper.pmid).where(SeedPaper.user_id == user_id)))
        embed_pmids(session, embedder, seeds)
    except EmbeddingError as e:
        session.rollback()
        log.warning("embedding for user %s failed, will retry on cli.py embed: %s", user_id, e)
        return False
    return refresh_profile_vector(session, user_id, embedder.model, coefs)


def refresh_all_profiles(session: Session, model: str, coefs: ProfileCoefficients) -> int:
    """Refresh every user's profile vector; returns how many users have one."""
    users = set(session.scalars(select(Topic.user_id))) | set(
        session.scalars(select(SeedPaper.user_id))
    )
    return sum(refresh_profile_vector(session, u, model, coefs) for u in users)
