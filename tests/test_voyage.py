import json

import httpx
import pytest

from app.embeddings.voyage import VOYAGE_BASE, VoyageEmbedder, VoyageError


def response(n: int, *, reverse: bool = False, tokens: int = 10) -> dict:
    data = [{"object": "embedding", "embedding": [float(i), 1.0], "index": i} for i in range(n)]
    if reverse:
        data.reverse()
    return {"object": "list", "data": data, "model": "voyage-4", "usage": {"total_tokens": tokens}}


def make(handler, sleeps: list[float] | None = None) -> VoyageEmbedder:
    http = httpx.Client(base_url=VOYAGE_BASE, transport=httpx.MockTransport(handler))
    return VoyageEmbedder(
        api_key="vk-test",
        http=http,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


def test_request_shape_and_order_restored_by_index() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        n = len(json.loads(request.content)["input"])
        return httpx.Response(200, json=response(n, reverse=True))

    result = make(handler).embed(["a", "b", "c"], "document")
    body = json.loads(seen[0].content)
    assert body == {"input": ["a", "b", "c"], "model": "voyage-4", "input_type": "document"}
    assert seen[0].headers["authorization"] == "Bearer vk-test"
    assert seen[0].url.path == "/v1/embeddings"
    assert [v[0] for v in result.vectors] == [0.0, 1.0, 2.0]
    assert result.tokens == 10


def test_splits_large_inputs_into_requests() -> None:
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        n = len(json.loads(request.content)["input"])
        sizes.append(n)
        return httpx.Response(200, json=response(n))

    result = make(handler).embed(["t"] * 130 + ["x" * 399_999, "yy"], "document")
    assert sizes == [128, 2, 1, 1]  # count limit, then the character budget
    assert len(result.vectors) == 132
    assert result.tokens == 40


def test_rate_limit_honours_retry_after() -> None:
    replies = iter(
        [
            httpx.Response(429, headers={"retry-after": "7"}),
            httpx.Response(503),
            httpx.Response(200, json=response(1)),
        ]
    )
    sleeps: list[float] = []
    result = make(lambda r: next(replies), sleeps).embed(["a"], "query")
    assert len(result.vectors) == 1
    assert sleeps == [7.0, 2]


def test_client_error_and_missing_items_raise() -> None:
    with pytest.raises(VoyageError, match="HTTP 400"):
        make(lambda r: httpx.Response(400, json={"detail": "bad model"})).embed(["a"], "query")
    with pytest.raises(VoyageError, match="expected 2"):
        make(lambda r: httpx.Response(200, json=response(1))).embed(["a", "b"], "query")
    with pytest.raises(VoyageError, match="unexpected response"):
        make(lambda r: httpx.Response(200, json={"oops": 1})).embed(["a"], "query")


def test_network_errors_are_retried_then_give_up() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("reset", request=request)
        return httpx.Response(200, json=response(1))

    sleeps: list[float] = []
    assert len(make(flaky, sleeps).embed(["a"], "query").vectors) == 1
    assert sleeps == [1]

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    with pytest.raises(VoyageError, match="unreachable"):
        make(down).embed(["a"], "query")


def test_persistent_server_errors_give_up_after_max_attempts() -> None:
    sleeps: list[float] = []
    with pytest.raises(VoyageError, match="HTTP 503 after retries"):
        make(lambda r: httpx.Response(503), sleeps).embed(["a"], "query")
    assert sleeps == [1, 2, 4, 8, 16]  # 6 attempts, 5 waits
