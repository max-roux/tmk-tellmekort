"""Weekly ingest, step 2: embed new papers (SPEC.md §6.2).

Idempotent: only papers without an embedding from the current model are embedded,
and each chunk is committed, so an interrupted run resumes where it stopped.
"""

from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Paper, PaperEmbedding
from app.embeddings.base import Embedder, paper_text

CHUNK = 512


@dataclass
class EmbedStats:
    embedded: int = 0
    tokens: int = 0


def _missing_stmt(model: str) -> Select[Paper]:
    return (
        select(Paper)
        .outerjoin(PaperEmbedding, PaperEmbedding.pmid == Paper.pmid)
        .where(or_(PaperEmbedding.pmid.is_(None), PaperEmbedding.model != model))
    )


def _missing(session: Session, model: str, limit: int) -> list[Paper]:
    stmt = _missing_stmt(model).order_by(Paper.entrez_date.desc(), Paper.pmid).limit(limit)
    return list(session.scalars(stmt))


def _missing_among(session: Session, model: str, pmids: list[str]) -> list[Paper]:
    return list(session.scalars(_missing_stmt(model).where(Paper.pmid.in_(pmids))))


def _store(session: Session, embedder: Embedder, papers: list[Paper], stats: EmbedStats) -> None:
    result = embedder.embed([paper_text(p.title, p.abstract) for p in papers], "document")
    rows = [
        {"pmid": p.pmid, "model": embedder.model, "vector": v}
        for p, v in zip(papers, result.vectors, strict=True)
    ]
    stmt = insert(PaperEmbedding).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PaperEmbedding.pmid],
        set_={
            "model": stmt.excluded.model,
            "vector": stmt.excluded.vector,
            "created_at": func.now(),
        },
    )
    session.execute(stmt)
    session.commit()
    stats.embedded += len(papers)
    stats.tokens += result.tokens


def embed_papers(session: Session, embedder: Embedder) -> EmbedStats:
    stats = EmbedStats()
    while papers := _missing(session, embedder.model, CHUNK):
        _store(session, embedder, papers, stats)
    return stats


def embed_pmids(session: Session, embedder: Embedder, pmids: list[str]) -> EmbedStats:
    """Embed just these papers (e.g. new seed papers) if they lack a current embedding."""
    stats = EmbedStats()
    if papers := _missing_among(session, embedder.model, pmids):
        _store(session, embedder, papers, stats)
    return stats
