"""Weekly ingest, step 4: full text for open-access papers (SPEC.md §6.4).

Fetched at grading time and not stored; only `papers.is_open_access` is recorded.
"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Paper
from app.sources.pubmed import PubMedClient


def fetch_full_texts(
    session: Session, client: PubMedClient, pmids: list[str], max_tokens: int
) -> dict[str, str]:
    """Full text by PMID for the open-access papers among `pmids`."""
    rows = session.execute(
        select(Paper.pmcid, Paper.pmid).where(Paper.pmid.in_(pmids), Paper.pmcid.is_not(None))
    ).all()
    by_pmcid = {pmcid: pmid for pmcid, pmid in rows if pmcid}
    if not by_pmcid:
        return {}
    texts: dict[str, str] = {}
    for article in client.fetch_pmc(list(by_pmcid), max_tokens):
        pmid = by_pmcid.get(article.pmcid)
        if pmid is None:
            continue
        session.execute(
            update(Paper).where(Paper.pmid == pmid).values(is_open_access=article.is_open_access)
        )
        if article.full_text:
            texts[pmid] = article.full_text
    session.commit()
    return texts
