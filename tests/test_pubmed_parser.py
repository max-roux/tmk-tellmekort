from datetime import date

import pytest

from app.sources.pubmed import (
    SPECIALTY_QUERY_PATH,
    PubMedError,
    load_specialty_query,
    parse_pubmed_xml,
)
from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def sample() -> dict[str, object]:
    result = parse_pubmed_xml((FIXTURES / "pubmed" / "efetch_sample.xml").read_bytes())
    return {"papers": {p.pmid: p for p in result.papers}, "skipped": result.skipped_no_abstract}


def test_fixture_papers_parsed_and_no_abstract_skipped(sample: dict) -> None:
    assert set(sample["papers"]) == {"42958619", "42949936", "42963307", "42963182", "42746924"}
    assert sample["skipped"] == ["42897076"]


def test_full_record_with_pmc_id(sample: dict) -> None:
    p = sample["papers"]["42958619"]
    assert p.doi == "10.1111/cid.70192"
    assert p.pmcid == "PMC13720216"
    assert p.entrez_date == date(2026, 10, 30)
    assert p.journal.startswith("Clinical implant dentistry")
    assert "Randomized Controlled Trial" in p.pub_types
    assert len(p.mesh_terms) > 0
    assert p.authors[0] == {"last": "Zuercher", "initials": "AN", "fore": "Anina N"}


def test_structured_abstract_keeps_section_labels(sample: dict) -> None:
    abstract = sample["papers"]["42958619"].abstract
    assert abstract.startswith("OBJECTIVE: ")
    assert "\n" in abstract


def test_unstructured_abstract(sample: dict) -> None:
    p = sample["papers"]["42963182"]
    assert "\n" not in p.abstract
    assert p.abstract.startswith("Van der Woude syndrome")


def test_missing_doi_and_non_oa(sample: dict) -> None:
    p = sample["papers"]["42949936"]
    assert p.doi is None
    assert p.pmcid is None
    assert "Case Reports" in p.pub_types


def test_medline_date_season_range(sample: dict) -> None:
    # PubDate is a <MedlineDate> range like "2026 Nov-Dec": pinned to its first month.
    assert sample["papers"]["42746924"].pub_date == date(2026, 11, 1)


def _wrap(article: str) -> bytes:
    return f"<PubmedArticleSet>{article}</PubmedArticleSet>".encode()


ARTICLE = """
<PubmedArticle>
  <MedlineCitation>
    <PMID Version="1">111</PMID>
    <Article>
      <Journal>
        <JournalIssue><PubDate><Year>2025</Year><Month>Feb</Month><Day>30</Day></PubDate></JournalIssue>
        <Title>J Test</Title>
      </Journal>
      <ArticleTitle>Effect of <i>X</i> on Y<sup>2</sup></ArticleTitle>
      <ELocationID EIdType="doi" ValidYN="Y">10.1/eloc</ELocationID>
      <Abstract><AbstractText>Plain text.</AbstractText></Abstract>
      <AuthorList>
        <Author><CollectiveName>OMFS Study Group</CollectiveName></Author>
        <Author><LastName>Doe</LastName></Author>
        <Author><ForeName>Nameless</ForeName></Author>
      </AuthorList>
      <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <History>
      <PubMedPubDate PubStatus="entrez">
        <Year>2025</Year><Month>3</Month><Day>4</Day>
      </PubMedPubDate>
    </History>
    <ArticleIdList><ArticleId IdType="pubmed">111</ArticleId></ArticleIdList>
  </PubmedData>
</PubmedArticle>
"""


def test_edge_cases_inline_markup_eloc_doi_authors_bad_day() -> None:
    (p,) = parse_pubmed_xml(_wrap(ARTICLE)).papers
    assert p.title == "Effect of X on Y2"
    assert p.doi == "10.1/eloc"
    assert p.authors == [{"collective": "OMFS Study Group"}, {"last": "Doe"}]
    assert p.pub_date == date(2025, 2, 1)  # Feb 30 does not exist
    assert p.entrez_date == date(2025, 3, 4)
    assert p.mesh_terms == []


def test_book_articles_ignored() -> None:
    xml = _wrap(
        "<PubmedBookArticle><BookDocument><PMID>9</PMID></BookDocument></PubmedBookArticle>"
    )
    result = parse_pubmed_xml(xml)
    assert result.papers == [] and result.skipped_no_abstract == []


def test_missing_entrez_date_raises() -> None:
    article = ARTICLE.replace('PubStatus="entrez"', 'PubStatus="received"')
    with pytest.raises(PubMedError, match="entrez"):
        parse_pubmed_xml(_wrap(article))


def test_specialty_query_strips_comments_and_whitespace(tmp_path) -> None:
    f = tmp_path / "q.txt"
    f.write_text("# comment\n(\n  a[Mesh]\n  OR b[ta]\n)\n# trailing\n")
    assert load_specialty_query(f) == "( a[Mesh] OR b[ta] )"


def test_real_specialty_query_loads() -> None:
    q = load_specialty_query(SPECIALTY_QUERY_PATH)
    assert '"Orthognathic Surgery"[Mesh]' in q
    assert "#" not in q
    assert q.count("(") == q.count(")")
