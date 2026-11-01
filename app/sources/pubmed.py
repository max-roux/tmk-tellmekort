"""NCBI E-utilities client and PubMed XML parser (SPEC.md §6.1).

The client is a thin wrapper over esearch/efetch with throttling and retries.
The parser is pure: XML bytes in, `ParsedPaper`s out.
"""

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from app.sources.pmc import PmcArticle, parse_pmc_xml

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EFETCH_BATCH_SIZE = 200
PMC_BATCH_SIZE = 20  # full-text XML runs to ~100 KB per article
# PubMed esearch cannot page past 10,000 results for one query.
ESEARCH_MAX_RESULTS = 9_999
SPECIALTY_QUERY_PATH = Path(__file__).with_name("specialty_query.txt")

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}
_RETRY_STATUS = {429, 500, 502, 503, 504}


class PubMedError(Exception):
    pass


def load_specialty_query(path: Path = SPECIALTY_QUERY_PATH) -> str:
    """Read the query file, dropping # comment lines and collapsing whitespace."""
    lines = [ln for ln in path.read_text().splitlines() if not ln.lstrip().startswith("#")]
    return " ".join(" ".join(lines).split())


# --------------------------------------------------------------------------- parser


@dataclass(frozen=True)
class ParsedPaper:
    pmid: str
    title: str
    abstract: str
    journal: str
    entrez_date: date
    doi: str | None = None
    pmcid: str | None = None
    pub_date: date | None = None
    pub_types: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    authors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ParseResult:
    papers: list[ParsedPaper]
    skipped_no_abstract: list[str]


def _text(el: ET.Element | None) -> str:
    """All text inside an element, including inline markup like <i> or <sup>."""
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def _int(s: str | None) -> int | None:
    return int(s) if s and s.strip().isdigit() else None


def _month(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip()
    if s.isdigit():
        return int(s)
    return _MONTHS.get(s[:3].lower())


def _safe_date(year: int | None, month: int | None, day: int | None) -> date | None:
    if year is None:
        return None
    try:
        return date(year, month or 1, day or 1)
    except ValueError:
        return date(year, month or 1, 1) if month and 1 <= month <= 12 else date(year, 1, 1)


def _parse_pub_date(article: ET.Element) -> date | None:
    """Journal issue date, falling back to the electronic article date.

    Partial dates are pinned to the first of the month/year.
    """
    pd = article.find("Journal/JournalIssue/PubDate")
    if pd is not None:
        year = _int(pd.findtext("Year"))
        if year is not None:
            return _safe_date(year, _month(pd.findtext("Month")), _int(pd.findtext("Day")))
        medline = pd.findtext("MedlineDate")  # e.g. "2024 Jan-Feb", "2023 Winter"
        if medline:
            m = re.match(r"(\d{4})(?:\s+([A-Za-z]{3}))?", medline)
            if m:
                return _safe_date(int(m.group(1)), _month(m.group(2)), None)
    ad = article.find("ArticleDate")
    if ad is not None:
        return _safe_date(
            _int(ad.findtext("Year")), _month(ad.findtext("Month")), _int(ad.findtext("Day"))
        )
    return None


def _parse_entrez_date(pubmed_data: ET.Element | None) -> date | None:
    if pubmed_data is None:
        return None
    for status in ("entrez", "pubmed"):
        el = pubmed_data.find(f"History/PubMedPubDate[@PubStatus='{status}']")
        if el is not None:
            return _safe_date(
                _int(el.findtext("Year")), _month(el.findtext("Month")), _int(el.findtext("Day"))
            )
    return None


def _parse_abstract(article: ET.Element) -> str:
    parts = []
    for el in article.findall("Abstract/AbstractText"):
        body = _text(el)
        if not body:
            continue
        label = el.get("Label")
        parts.append(f"{label}: {body}" if label else body)
    return "\n".join(parts)


def _parse_authors(article: ET.Element) -> list[dict[str, Any]]:
    authors: list[dict[str, Any]] = []
    for a in article.findall("AuthorList/Author"):
        collective = a.findtext("CollectiveName")
        if collective:
            authors.append({"collective": collective.strip()})
            continue
        last = a.findtext("LastName")
        if not last:
            continue
        author: dict[str, Any] = {"last": last.strip()}
        if initials := a.findtext("Initials"):
            author["initials"] = initials.strip()
        if fore := a.findtext("ForeName"):
            author["fore"] = fore.strip()
        authors.append(author)
    return authors


def _article_id(pubmed_data: ET.Element | None, id_type: str) -> str | None:
    if pubmed_data is None:
        return None
    el = pubmed_data.find(f"ArticleIdList/ArticleId[@IdType='{id_type}']")
    return el.text.strip() if el is not None and el.text else None


def _citation(node: ET.Element) -> tuple[ET.Element, str, ET.Element]:
    """(MedlineCitation, PMID, Article), or PubMedError for a malformed record."""
    citation = node.find("MedlineCitation")
    if citation is None:
        raise PubMedError("PubmedArticle without MedlineCitation")
    pmid = (citation.findtext("PMID") or "").strip()
    article = citation.find("Article")
    if not pmid or article is None:
        raise PubMedError(f"Malformed PubmedArticle (pmid={pmid!r})")
    return citation, pmid, article


def _doi(article: ET.Element, pubmed_data: ET.Element | None) -> str | None:
    """From the article ID list, else the electronic location."""
    doi = _article_id(pubmed_data, "doi")
    if doi is not None:
        return doi
    eloc = article.find("ELocationID[@EIdType='doi']")
    return eloc.text.strip() if eloc is not None and eloc.text else None


def _first_text(article: ET.Element, *paths: str) -> str:
    return next((t for p in paths if (t := _text(article.find(p)))), "")


def _parse_article(node: ET.Element) -> ParsedPaper | str:
    """Return a ParsedPaper, or the PMID if the record has no abstract."""
    citation, pmid, article = _citation(node)

    abstract = _parse_abstract(article)
    if not abstract:
        return pmid

    pubmed_data = node.find("PubmedData")
    entrez = _parse_entrez_date(pubmed_data)
    if entrez is None:
        raise PubMedError(f"PMID {pmid}: no entrez date")

    return ParsedPaper(
        pmid=pmid,
        title=_first_text(article, "ArticleTitle", "VernacularTitle"),
        abstract=abstract,
        journal=_first_text(article, "Journal/Title", "Journal/ISOAbbreviation"),
        entrez_date=entrez,
        doi=_doi(article, pubmed_data),
        pmcid=_article_id(pubmed_data, "pmc"),
        pub_date=_parse_pub_date(article),
        pub_types=[_text(pt) for pt in article.findall("PublicationTypeList/PublicationType")],
        mesh_terms=[
            _text(d) for d in citation.findall("MeshHeadingList/MeshHeading/DescriptorName")
        ],
        authors=_parse_authors(article),
    )


def parse_pubmed_xml(xml: bytes) -> ParseResult:
    """Parse an efetch `PubmedArticleSet`. Book records are ignored."""
    root = ET.fromstring(xml)
    papers: list[ParsedPaper] = []
    skipped: list[str] = []
    for node in root.findall("PubmedArticle"):
        parsed = _parse_article(node)
        if isinstance(parsed, str):
            skipped.append(parsed)
        else:
            papers.append(parsed)
    return ParseResult(papers=papers, skipped_no_abstract=skipped)


# --------------------------------------------------------------------------- client


class PubMedClient:
    """Thin E-utilities client: esearch for PMIDs, efetch for records.

    Throttles to NCBI's limit (10 req/s with an API key, 3 without) and retries
    transient failures with exponential backoff.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        email: str = "",
        tool: str = "maxfac-recommender",
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_attempts: int = 4,
    ) -> None:
        self._params: dict[str, str] = {"tool": tool}
        if email:
            self._params["email"] = email
        if api_key:
            self._params["api_key"] = api_key
        self._min_interval = 1 / 10 if api_key else 1 / 3
        self._http = http or httpx.Client(base_url=EUTILS_BASE, timeout=60)
        self._sleep = sleep
        self._clock = clock
        self._max_attempts = max_attempts
        self._last_request = float("-inf")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "PubMedClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, endpoint: str, data: dict[str, str]) -> httpx.Response:
        payload = {**self._params, **data}
        for attempt in range(1, self._max_attempts + 1):
            wait = self._last_request + self._min_interval - self._clock()
            if wait > 0:
                self._sleep(wait)
            self._last_request = self._clock()
            try:
                resp = self._http.post(endpoint, data=payload)
            except httpx.TransportError as e:
                if attempt == self._max_attempts:
                    raise PubMedError(f"{endpoint}: {e}") from e
            else:
                if resp.status_code not in _RETRY_STATUS:
                    if resp.is_error:
                        raise PubMedError(f"{endpoint}: HTTP {resp.status_code}")
                    return resp
                if attempt == self._max_attempts:
                    raise PubMedError(f"{endpoint}: HTTP {resp.status_code} after retries")
            self._sleep(2 ** (attempt - 1))
        raise AssertionError("unreachable")

    def search(self, query: str, mindate: date, maxdate: date) -> list[str]:
        """PMIDs matching `query` with an entrez date in [mindate, maxdate]."""
        resp = self._request(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": query,
                "datetype": "edat",
                "mindate": mindate.strftime("%Y/%m/%d"),
                "maxdate": maxdate.strftime("%Y/%m/%d"),
                "retmax": str(ESEARCH_MAX_RESULTS),
                "retmode": "json",
            },
        )
        result = resp.json().get("esearchresult", {})
        if "ERROR" in result:
            raise PubMedError(f"esearch: {result['ERROR']}")
        count = int(result.get("count", 0))
        if count > ESEARCH_MAX_RESULTS:
            raise PubMedError(
                f"esearch returned {count} results for {mindate}..{maxdate}; use a shorter window"
            )
        return [str(p) for p in result.get("idlist", [])]

    def find(self, term: str, retmax: int = 20) -> list[str]:
        """PMIDs matching `term` with no date limit, e.g. `"10.1000/xyz"[doi]`."""
        resp = self._request(
            "esearch.fcgi",
            {"db": "pubmed", "term": term, "retmax": str(retmax), "retmode": "json"},
        )
        result = resp.json().get("esearchresult", {})
        if "ERROR" in result:
            raise PubMedError(f"esearch: {result['ERROR']}")
        return [str(p) for p in result.get("idlist", [])]

    def fetch(self, pmids: list[str]) -> ParseResult:
        """Fetch and parse records, in batches of EFETCH_BATCH_SIZE."""
        papers: list[ParsedPaper] = []
        skipped: list[str] = []
        for i in range(0, len(pmids), EFETCH_BATCH_SIZE):
            batch = pmids[i : i + EFETCH_BATCH_SIZE]
            resp = self._request(
                "efetch.fcgi", {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
            )
            result = parse_pubmed_xml(resp.content)
            papers.extend(result.papers)
            skipped.extend(result.skipped_no_abstract)
        return ParseResult(papers=papers, skipped_no_abstract=skipped)

    def fetch_pmc(self, pmcids: list[str], max_tokens: int) -> list[PmcArticle]:
        """Fetch PMC articles (JATS XML) and reduce open-access ones to graded text."""
        articles: list[PmcArticle] = []
        ids = [p.removeprefix("PMC") for p in pmcids]
        for i in range(0, len(ids), PMC_BATCH_SIZE):
            batch = ids[i : i + PMC_BATCH_SIZE]
            resp = self._request("efetch.fcgi", {"db": "pmc", "id": ",".join(batch)})
            articles.extend(parse_pmc_xml(resp.content, max_tokens))
        return articles
