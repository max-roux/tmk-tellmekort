import httpx
import pytest

from app.sources.pmc import CHARS_PER_TOKEN, parse_pmc_xml
from app.sources.pubmed import EUTILS_BASE, PubMedClient
from tests.conftest import FIXTURES

XML = (FIXTURES / "pmc" / "efetch_pmc.xml").read_bytes()


@pytest.fixture(scope="module")
def articles() -> dict:
    return {a.pmcid: a for a in parse_pmc_xml(XML, max_tokens=12_000)}


def test_no_licence_no_body_is_not_open_access(articles: dict) -> None:
    a = articles["PMC13437821"]
    assert not a.is_open_access and a.full_text is None


def test_cc_by_article_text_methods_first_without_back_matter(articles: dict) -> None:
    a = articles["PMC13720216"]
    assert a.is_open_access
    text = a.full_text
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Methods",
        "## Results",
        "## Introduction",
        "## Discussion",
        "## Conclusions",
    ]
    assert "### Study Design" in text
    # Figures, tables, references and back matter are dropped.
    assert "Schematic illustration of buccal bone thickness" not in text
    assert "Participants baseline characteristics." not in text
    assert "Consensus Report of Workgroup 4" not in text
    assert "## Funding" not in text and "Conflicts of Interest" not in text
    assert "[truncated]" not in text


def test_truncates_to_token_budget_at_a_word() -> None:
    (_, a) = parse_pmc_xml(XML, max_tokens=500)
    text = a.full_text
    assert text.startswith("## Methods")
    assert text.endswith("[truncated]")
    assert len(text) <= 500 * CHARS_PER_TOKEN + 20


def wrap(licence: str, body: str) -> bytes:
    return f"""<pmc-articleset><article xmlns:xlink="http://www.w3.org/1999/xlink">
      <front><article-meta><article-id pub-id-type="pmcid">PMC1</article-id>
      <permissions>{licence}</permissions></article-meta></front>
      <body>{body}</body></article></pmc-articleset>""".encode()


@pytest.mark.parametrize(
    ("licence", "oa"),
    [
        ('<license license-type="open-access"><license-p>x</license-p></license>', True),
        ('<license xlink:href="https://creativecommons.org/licenses/by-nc/4.0/"/>', True),
        ("<license><license-p>All rights reserved.</license-p></license>", False),
        ("", False),
    ],
)
def test_open_access_detection(licence: str, oa: bool) -> None:
    (a,) = parse_pmc_xml(wrap(licence, "<p>Loose paragraph.</p>"), 1000)
    assert a.is_open_access is oa
    assert (a.full_text == "## Other\n\nLoose paragraph.") is oa


def test_inline_markup_kept_tables_inside_paragraphs_dropped() -> None:
    body = (
        '<sec sec-type="results"><title>Results</title>'
        "<p>Gain was <italic>2 mm</italic> (<xref>12</xref>)."
        "<table-wrap><caption><p>Table 1</p></caption></table-wrap> Done.</p></sec>"
        "<sec><title>Acknowledgments</title><p>Thanks.</p></sec>"
    )
    (a,) = parse_pmc_xml(wrap('<license license-type="open-access"/>', body), 1000)
    assert a.full_text == "## Results\n\nGain was 2 mm (12). Done."


def test_client_fetches_pmc_in_batches_of_20() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs

        calls.append({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, content=XML)

    http = httpx.Client(base_url=EUTILS_BASE, transport=httpx.MockTransport(handler))
    client = PubMedClient(api_key="k", http=http, sleep=lambda s: None)
    out = client.fetch_pmc([f"PMC{i}" for i in range(25)], max_tokens=1000)
    assert [len(c["id"].split(",")) for c in calls] == [20, 5]
    assert calls[0]["db"] == "pmc" and calls[0]["id"].startswith("0,1,")
    assert len(out) == 4


def test_case_presentation_comes_before_introduction() -> None:
    body = (
        "<sec><title>Introduction</title><p>Intro.</p></sec>"
        "<sec><title>Case Presentation</title><p>A 54-year-old man.</p></sec>"
    )
    (a,) = parse_pmc_xml(wrap('<license license-type="open-access"/>', body), 1000)
    assert a.full_text == "## Case\n\nA 54-year-old man.\n\n## Introduction\n\nIntro."
