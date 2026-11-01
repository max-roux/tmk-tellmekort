from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.users import add_user
from app.db.models import Candidate, Grade, Paper, PaperEmbedding
from app.domain.ranking import ProfileCoefficients
from app.domain.seeds import SeedRefs
from app.grading.grader import Grader
from app.jobs.embed_papers import embed_papers
from app.jobs.full_text import fetch_full_texts
from app.jobs.grade_papers import Polling, grade_batch
from app.jobs.narrow_candidates import narrow, selected_ungraded, user_references, week_of
from app.jobs.weekly_ingest import store_papers
from app.profiles import service
from app.profiles.topics import ProposedTopic
from app.sources.pmc import PmcArticle
from app.sources.pubmed import parse_pubmed_xml
from tests.conftest import FIXTURES
from tests.fakes import FakeAnthropic, FakeEmbedder, FakePubMed, batch_lines, message

pytestmark = pytest.mark.db

SAMPLE = parse_pubmed_xml((FIXTURES / "pubmed" / "efetch_sample.xml").read_bytes()).papers
WEEK = date(2026, 10, 26)
NEXT_WEEK = date(2026, 11, 2)
# Entrez dates in the fixture: four papers 2026-10-28..30, one (42746924) on 2026-09-16.
OCT = {"since": date(2026, 10, 24)}


@pytest.fixture
def session(db_session: Session) -> Session:
    store_papers(db_session, SAMPLE)
    return db_session


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_week_of_is_monday() -> None:
    assert week_of(date(2026, 11, 1)) == date(2026, 10, 26)  # Sunday
    assert week_of(date(2026, 10, 26)) == date(2026, 10, 26)


def test_embed_is_idempotent_and_reembeds_on_model_change(session: Session) -> None:
    e = FakeEmbedder()
    stats = embed_papers(session, e)
    assert stats.embedded == 5 and e.calls == [(5, "document")]
    assert len(session.get(PaperEmbedding, "42958619").vector) == 1024
    assert embed_papers(session, e).embedded == 0

    newer = FakeEmbedder(model="voyage-5")
    assert embed_papers(session, newer).embedded == 5
    assert set(session.scalars(select(PaperEmbedding.model))) == {"voyage-5"}


def test_narrow_selects_closest_to_anchor_and_reruns_cleanly(session: Session) -> None:
    # Two papers point along the anchor; the others are random (near-orthogonal in 1024-d).
    e = FakeEmbedder(
        pinned={
            "ANCHOR": [1.0, 0.0],
            "Orofacial Cleft Characteristics": [0.9, 0.1],
            "Pink lipoma": [0.6, 0.4],
        }
    )
    embed_papers(session, e)
    stats = narrow(session, e, **OCT, week=WEEK, limit=2, anchor_text="ANCHOR")
    assert (stats.candidates, stats.selected, stats.missing_embeddings) == (4, 2, 0)
    assert e.calls[-1] == (1, "query")
    selected = set(session.scalars(select(Candidate.pmid).where(Candidate.selected_for_grading)))
    assert selected == {"42963182", "42949936"}
    assert session.get(Candidate, ("42746924", WEEK)) is None  # before `since`

    # A rerun overwrites the week's rows.
    narrow(session, e, **OCT, week=WEEK, limit=1, anchor_text="ANCHOR")
    assert count(session, Candidate) == 4
    selected = set(session.scalars(select(Candidate.pmid).where(Candidate.selected_for_grading)))
    assert selected == {"42963182"}


def test_narrow_scores_late_arrivals_once(db_session: Session) -> None:
    late, early = SAMPLE[-1], SAMPLE[:-1]  # 42746924 has the oldest entrez date
    since = date(2026, 9, 1)
    e = FakeEmbedder()
    store_papers(db_session, early)
    embed_papers(db_session, e)
    assert narrow(db_session, e, since=since, week=WEEK, limit=1, anchor_text="A").candidates == 4

    # Stored after this week's run, with an entrez date inside last week's range.
    store_papers(db_session, [late])
    embed_papers(db_session, e)
    stats = narrow(db_session, e, since=since, week=NEXT_WEEK, limit=5, anchor_text="A")
    assert (stats.candidates, stats.selected) == (1, 1)
    assert db_session.get(Candidate, (late.pmid, NEXT_WEEK)) is not None
    following = NEXT_WEEK + timedelta(days=7)
    assert (
        narrow(db_session, e, since=since, week=following, limit=5, anchor_text="A").candidates == 0
    )


def test_narrow_reports_missing_embeddings(session: Session) -> None:
    stats = narrow(session, FakeEmbedder(), **OCT, week=WEEK, limit=5, anchor_text="A")
    assert (stats.candidates, stats.missing_embeddings) == (0, 4)


def test_selected_ungraded_excludes_graded(session: Session) -> None:
    e = FakeEmbedder()
    embed_papers(session, e)
    narrow(session, e, **OCT, week=WEEK, limit=10, anchor_text="A")
    assert len(selected_ungraded(session)) == 4
    grader = Grader(FakeAnthropic(sync=[message()]), model="claude-sonnet-5-5", effort="low")  # type: ignore[arg-type]
    from app.jobs.grade_papers import grade_sync

    grade_sync(session, grader, ["42958619"], date(2026, 11, 1))
    assert "42958619" not in selected_ungraded(session)
    assert len(selected_ungraded(session, limit=2)) == 2


class FakePmc:
    def __init__(self, articles: list[PmcArticle]) -> None:
        self.articles = articles
        self.requested: list[str] = []

    def fetch_pmc(self, pmcids: list[str], max_tokens: int) -> list[PmcArticle]:
        self.requested = pmcids
        return self.articles


def test_full_texts_set_open_access_flag(session: Session) -> None:
    session.get(Paper, "42963182").pmcid = "PMC999"  # give a second paper a PMCID
    session.commit()
    pmc = FakePmc(
        [PmcArticle("PMC13720216", True, "## Methods\n\nfull"), PmcArticle("PMC999", False, None)]
    )
    texts = fetch_full_texts(
        session,
        pmc,
        ["42958619", "42963182", "42949936"],
        max_tokens=12_000,  # type: ignore[arg-type]
    )
    assert texts == {"42958619": "## Methods\n\nfull"}
    assert sorted(pmc.requested) == ["PMC13720216", "PMC999"]
    assert session.get(Paper, "42958619").is_open_access is True
    assert session.get(Paper, "42963182").is_open_access is False
    assert fetch_full_texts(session, pmc, ["42949936"], 12_000) == {}  # type: ignore[arg-type]


def test_batch_with_full_text_records_source_and_keeps_depth(session: Session) -> None:
    fake = FakeAnthropic(batch_results=batch_lines()[:1])  # only 42958619 succeeds
    grader = Grader(fake, model="claude-sonnet-5-5", effort="low")  # type: ignore[arg-type]
    texts = {"42958619": "## Methods\n\nfull text here"}
    grade_batch(
        session, grader, ["42958619"], date(2026, 11, 1), Polling(sleep=lambda s: None), texts
    )
    request = fake.messages.batches.created[0][0]  # type: ignore[attr-defined]
    assert "<full_text>\n## Methods" in request["params"]["messages"][0]["content"]
    g = session.scalars(select(Grade)).one()
    assert g.input_source == "full_text"
    assert g.depth == 5  # not clamped: graded from full text


def test_user_references_feed_narrowing(session: Session) -> None:
    e = FakeEmbedder()
    embed_papers(session, e)
    user = add_user(session, "surgeon@example.com")
    service.replace_topics(
        session, user.id, [ProposedTopic("A", "alpha"), ProposedTopic("B", "beta")], "manual"
    )
    service.add_seeds(session, user.id, SeedRefs(pmids=["42949936"]), FakePubMed())  # type: ignore[arg-type]
    service.sync_embeddings(session, e, user.id, ProfileCoefficients())

    refs = user_references(session, "voyage-4")
    assert len(refs.vectors) == 3  # profile vector + 2 topics
    assert user_references(session, "voyage-5").vectors == []

    stats = narrow(
        session,
        e,
        **OCT,
        week=WEEK,
        limit=0,
        anchor_text="A",
        profile_vectors=refs.vectors,
    )
    assert stats.selected == 0  # seeds shape the profile but are not forced into grading
