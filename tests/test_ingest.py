from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Paper
from app.jobs.weekly_ingest import IngestStats, date_windows, ingest
from app.sources.pubmed import ParseResult, parse_pubmed_xml
from tests.conftest import FIXTURES

SAMPLE = parse_pubmed_xml((FIXTURES / "pubmed" / "efetch_sample.xml").read_bytes())
ALL_PMIDS = [p.pmid for p in SAMPLE.papers] + SAMPLE.skipped_no_abstract


class FakePubMed:
    """Returns the recorded sample for the first window, nothing for later ones."""

    def __init__(self) -> None:
        self.searches: list[tuple[date, date]] = []
        self.fetched: list[list[str]] = []

    def search(self, query: str, mindate: date, maxdate: date) -> list[str]:
        self.searches.append((mindate, maxdate))
        return ALL_PMIDS if len(self.searches) == 1 else []

    def fetch(self, pmids: list[str]) -> ParseResult:
        self.fetched.append(pmids)
        return ParseResult(
            papers=[p for p in SAMPLE.papers if p.pmid in pmids],
            skipped_no_abstract=[p for p in SAMPLE.skipped_no_abstract if p in pmids],
        )


def test_date_windows_cover_range_inclusively() -> None:
    windows = list(date_windows(date(2026, 1, 1), date(2026, 1, 20)))
    assert windows == [
        (date(2026, 1, 1), date(2026, 1, 7)),
        (date(2026, 1, 8), date(2026, 1, 14)),
        (date(2026, 1, 15), date(2026, 1, 20)),
    ]
    assert list(date_windows(date(2026, 1, 1), date(2026, 1, 1))) == [
        (date(2026, 1, 1), date(2026, 1, 1))
    ]
    assert len(list(date_windows(date(2026, 8, 3), date(2026, 10, 31)))) == 13  # 90-day backfill


@pytest.mark.db
def test_ingest_stores_papers_and_is_idempotent(db_session: Session) -> None:
    client = FakePubMed()
    first = ingest(db_session, client, "q", date(2026, 10, 18), date(2026, 10, 31))  # type: ignore[arg-type]

    assert client.searches == [
        (date(2026, 10, 18), date(2026, 10, 24)),
        (date(2026, 10, 25), date(2026, 10, 31)),
    ]
    assert first == IngestStats(found=6, already_stored=0, stored=5, skipped_no_abstract=1)
    paper = db_session.get(Paper, "42958619")
    assert paper is not None
    assert paper.pmcid == "PMC13720216"
    assert paper.authors[0]["last"] == "Zuercher"
    assert paper.is_open_access is False

    rerun_client = FakePubMed()
    second = ingest(db_session, rerun_client, "q", date(2026, 10, 18), date(2026, 10, 31))  # type: ignore[arg-type]
    assert second == IngestStats(found=6, already_stored=5, stored=0, skipped_no_abstract=1)
    # Only the no-abstract record is re-fetched; stored papers are not.
    assert rerun_client.fetched == [SAMPLE.skipped_no_abstract]
    assert db_session.scalar(select(func.count()).select_from(Paper)) == 5
