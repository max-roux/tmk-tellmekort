"""Weekly ingest, step 1: fetch from PubMed and store papers (SPEC.md §6.1).

Idempotent: papers already stored are not re-fetched, and inserts ignore conflicts,
so re-running for the same window adds nothing.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Paper
from app.sources.pubmed import ParsedPaper, PubMedClient

# Keeps each esearch well under PubMed's 10k-result paging cap during backfill.
WINDOW_DAYS = 7


@dataclass
class IngestStats:
    found: int = 0
    already_stored: int = 0
    stored: int = 0
    skipped_no_abstract: int = 0


def date_windows(start: date, end: date, days: int = WINDOW_DAYS) -> Iterator[tuple[date, date]]:
    """Split [start, end] (inclusive) into consecutive windows of at most `days` days."""
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=days - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def _row(p: ParsedPaper) -> dict[str, object]:
    return {
        "pmid": p.pmid,
        "doi": p.doi,
        "pmcid": p.pmcid,
        "title": p.title,
        "abstract": p.abstract,
        "journal": p.journal,
        "pub_types": p.pub_types,
        "mesh_terms": p.mesh_terms,
        "authors": p.authors,
        "entrez_date": p.entrez_date,
        "pub_date": p.pub_date,
    }


def store_papers(session: Session, papers: list[ParsedPaper]) -> int:
    """Insert papers, ignoring PMIDs already present. Returns the number inserted."""
    if not papers:
        return 0
    stmt = (
        insert(Paper)
        .values([_row(p) for p in papers])
        .on_conflict_do_nothing(index_elements=[Paper.pmid])
        .returning(Paper.pmid)
    )
    inserted = len(session.execute(stmt).all())
    session.commit()
    return inserted


def ingest(
    session: Session, client: PubMedClient, query: str, start: date, end: date
) -> IngestStats:
    """Fetch and store every paper matching `query` with entrez date in [start, end]."""
    stats = IngestStats()
    for lo, hi in date_windows(start, end):
        pmids = client.search(query, lo, hi)
        stats.found += len(pmids)
        if not pmids:
            continue
        existing = set(session.scalars(select(Paper.pmid).where(Paper.pmid.in_(pmids))))
        stats.already_stored += len(existing)
        new = [p for p in pmids if p not in existing]
        if not new:
            continue
        result = client.fetch(new)
        stats.skipped_no_abstract += len(result.skipped_no_abstract)
        stats.stored += store_papers(session, result.papers)
    return stats
