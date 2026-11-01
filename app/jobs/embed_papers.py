"""Weekly ingest, step 2: embed new papers (SPEC.md §6.2).

Idempotent: only papers without an embedding from the current model are embedded,
and each chunk is committed, so an interrupted run resumes where it stopped.
"""

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Paper, PaperEmbedding
from app.embeddings.base import Embedder, paper_text

CHUNK = 512


@dataclass
class EmbedStats:
    embedded: int = 0
    tokens: int = 0


def _missing(session: Session, model: str, limit: int) -> list[Paper]:
    stmt = (
        select(Paper)
        .outerjoin(PaperEmbedding, PaperEmbedding.pmid == Paper.pmid)
        .where(or_(PaperEmbedding.pmid.is_(None), PaperEmbedding.model != model))
        .order_by(Paper.entrez_date.desc(), Paper.pmid)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def embed_papers(session: Session, embedder: Embedder) -> EmbedStats:
    stats = EmbedStats()
    while papers := _missing(session, embedder.model, CHUNK):
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
    return stats
