"""Voyage AI embeddings client (POST /v1/embeddings).

Splits input into requests within Voyage's limits and retries rate limits and
server errors, honouring Retry-After.
"""

import time
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ValidationError

from app.embeddings.base import EmbeddingError, Embeddings, InputType

VOYAGE_BASE = "https://api.voyageai.com/v1"
MAX_TEXTS_PER_REQUEST = 128
# Voyage allows 320K tokens per request for voyage-4; stay well under it.
MAX_CHARS_PER_REQUEST = 400_000  # ~100K tokens at ~4 chars/token
_RETRY_STATUS = {429, 500, 502, 503, 504}


class VoyageError(EmbeddingError):
    pass


class _Item(BaseModel):
    embedding: list[float]
    index: int


class _Usage(BaseModel):
    total_tokens: int = 0


class _Response(BaseModel):
    data: list[_Item]
    usage: _Usage = _Usage()


def _batches(texts: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    chars = 0
    for t in texts:
        if current and (
            len(current) >= MAX_TEXTS_PER_REQUEST or chars + len(t) > MAX_CHARS_PER_REQUEST
        ):
            batches.append(current)
            current, chars = [], 0
        current.append(t)
        chars += len(t)
    if current:
        batches.append(current)
    return batches


def _parse(resp: httpx.Response) -> _Response:
    if resp.is_error:
        # The body explains bad requests; it never contains the key.
        raise VoyageError(f"embeddings: HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        return _Response.model_validate_json(resp.content)
    except ValidationError as e:
        raise VoyageError(f"embeddings: unexpected response: {e}") from e


def _delay(resp: httpx.Response | None, attempt: int) -> float:
    """Retry-After when the server sends one, else exponential backoff."""
    retry_after = resp.headers.get("retry-after", "") if resp is not None else ""
    return float(retry_after) if retry_after.isdigit() else 2 ** (attempt - 1)


class VoyageEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "voyage-4",
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 6,
    ) -> None:
        self._model = model
        self._http = http or httpx.Client(base_url=VOYAGE_BASE, timeout=120)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._sleep = sleep
        self._max_attempts = max_attempts

    @property
    def model(self) -> str:
        return self._model

    def close(self) -> None:
        self._http.close()

    def _send(self, payload: dict[str, object], *, last: bool) -> httpx.Response | None:
        """The response, or None after a network error worth retrying."""
        try:
            return self._http.post("/embeddings", json=payload, headers=self._headers)
        except httpx.TransportError as e:
            if last:
                raise VoyageError(f"embeddings: {e}") from e
            return None

    def _post(self, payload: dict[str, object]) -> _Response:
        for attempt in range(1, self._max_attempts + 1):
            last = attempt == self._max_attempts
            resp = self._send(payload, last=last)
            if resp is not None and resp.status_code not in _RETRY_STATUS:
                return _parse(resp)
            if resp is not None and last:
                raise VoyageError(f"embeddings: HTTP {resp.status_code} after retries")
            self._sleep(_delay(resp, attempt))
        raise AssertionError("unreachable")

    def embed(self, texts: list[str], input_type: InputType) -> Embeddings:
        vectors: list[list[float]] = []
        tokens = 0
        for batch in _batches(texts):
            resp = self._post({"input": batch, "model": self._model, "input_type": input_type})
            items = sorted(resp.data, key=lambda d: d.index)
            if [i.index for i in items] != list(range(len(batch))):
                raise VoyageError(f"expected {len(batch)} embeddings, got {len(items)}")
            vectors.extend(i.embedding for i in items)
            tokens += resp.usage.total_tokens
        return Embeddings(vectors=vectors, tokens=tokens)
