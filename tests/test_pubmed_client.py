from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest

from app.sources.pubmed import EUTILS_BASE, PubMedClient, PubMedError
from tests.conftest import FIXTURES

EFETCH_XML = (FIXTURES / "pubmed" / "efetch_sample.xml").read_bytes()
ESEARCH_JSON = (FIXTURES / "pubmed" / "esearch_week.json").read_bytes()


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def make_client(handler, *, api_key: str = "k") -> tuple[PubMedClient, FakeTime]:
    t = FakeTime()
    http = httpx.Client(base_url=EUTILS_BASE, transport=httpx.MockTransport(handler))
    client = PubMedClient(
        api_key=api_key, email="ops@example.com", http=http, sleep=t.sleep, clock=t.clock
    )
    return client, t


def form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_search_sends_identity_and_date_window() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(form(request))
        return httpx.Response(200, content=ESEARCH_JSON)

    client, _ = make_client(handler)
    pmids = client.search("q", date(2026, 10, 25), date(2026, 10, 31))

    assert len(pmids) > 0 and all(p.isdigit() for p in pmids)
    params = seen[0]
    assert params["api_key"] == "k"
    assert params["email"] == "ops@example.com"
    assert params["tool"] == "maxfac-recommender"
    assert (params["datetype"], params["mindate"], params["maxdate"]) == (
        "edat",
        "2026/10/25",
        "2026/10/31",
    )


def test_search_rejects_windows_over_paging_cap() -> None:
    body = {"esearchresult": {"count": "12000", "idlist": []}}
    client, _ = make_client(lambda r: httpx.Response(200, json=body))
    with pytest.raises(PubMedError, match="shorter window"):
        client.search("q", date(2026, 1, 1), date(2026, 12, 31))


def test_search_surfaces_esearch_error() -> None:
    body = {"esearchresult": {"ERROR": "Invalid query"}}
    client, _ = make_client(lambda r: httpx.Response(200, json=body))
    with pytest.raises(PubMedError, match="Invalid query"):
        client.search("q", date(2026, 1, 1), date(2026, 1, 7))


def test_fetch_batches_200_ids_per_request() -> None:
    batches: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        batches.append(len(form(request)["id"].split(",")))
        return httpx.Response(200, content=EFETCH_XML)

    client, _ = make_client(handler)
    result = client.fetch([str(i) for i in range(450)])

    assert batches == [200, 200, 50]
    assert len(result.papers) == 15  # fixture has 5 papers, returned 3 times
    assert len(result.skipped_no_abstract) == 3


def test_throttles_to_ten_per_second_with_key() -> None:
    client, t = make_client(lambda r: httpx.Response(200, content=EFETCH_XML))
    client.fetch(["1"] * 600)  # 3 requests back to back
    assert t.sleeps == pytest.approx([0.1, 0.1])


def test_throttles_to_three_per_second_without_key() -> None:
    client, t = make_client(lambda r: httpx.Response(200, content=EFETCH_XML), api_key="")
    client.fetch(["1"] * 400)
    assert t.sleeps == pytest.approx([1 / 3])


def test_retries_transient_errors_with_backoff() -> None:
    responses = iter(
        [httpx.Response(503), httpx.Response(429), httpx.Response(200, content=EFETCH_XML)]
    )
    client, t = make_client(lambda r: next(responses))
    result = client.fetch(["1"])
    assert len(result.papers) == 5
    assert 1 in t.sleeps and 2 in t.sleeps


def test_retries_transport_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, content=EFETCH_XML)

    client, _ = make_client(handler)
    assert len(client.fetch(["1"]).papers) == 5


def test_gives_up_after_max_attempts() -> None:
    client, _ = make_client(lambda r: httpx.Response(502))
    with pytest.raises(PubMedError, match="after retries"):
        client.fetch(["1"])


def test_client_error_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    client, _ = make_client(handler)
    with pytest.raises(PubMedError, match="HTTP 400"):
        client.fetch(["1"])
    assert calls == 1
