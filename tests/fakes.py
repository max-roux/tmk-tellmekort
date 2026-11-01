"""In-memory stand-ins for the Anthropic client, returning SDK model objects from fixtures."""

import json
from collections.abc import Iterator
from typing import Any

from anthropic.types import Message
from anthropic.types.beta import BetaMessage
from anthropic.types.messages import MessageBatch, MessageBatchIndividualResponse

from tests.conftest import FIXTURES

ANTHROPIC = FIXTURES / "anthropic"


def load_json(name: str) -> dict[str, Any]:
    return json.loads((ANTHROPIC / name).read_text())


def message(name: str = "message_grade_ok.json", **overrides: Any) -> dict[str, Any]:
    return {**load_json(name), **overrides}


def batch_lines() -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in (ANTHROPIC / "batch_results.jsonl").read_text().splitlines()
    ]


def _batch(batch_id: str, status: str) -> MessageBatch:
    return MessageBatch.model_validate(
        {
            "id": batch_id,
            "type": "message_batch",
            "processing_status": status,
            "request_counts": {
                "processing": 0,
                "succeeded": 0,
                "errored": 0,
                "canceled": 0,
                "expired": 0,
            },
            "created_at": "2026-11-01T00:00:00Z",
            "expires_at": "2026-11-02T00:00:00Z",
            "ended_at": None,
            "archived_at": None,
            "cancel_initiated_at": None,
            "results_url": None,
        }
    )


class FakeBetaMessages:
    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> BetaMessage:
        self.calls.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return BetaMessage.model_validate(r)


class FakeBatches:
    def __init__(self, results: list[dict[str, Any]], polls_until_ended: int = 0) -> None:
        self.results_data = results
        self.polls_until_ended = polls_until_ended
        self.created: list[list[Any]] = []
        self.retrieved = 0

    def create(self, *, requests: list[Any]) -> MessageBatch:
        self.created.append(requests)
        return _batch(f"msgbatch_{len(self.created)}", "in_progress")

    def retrieve(self, batch_id: str) -> MessageBatch:
        self.retrieved += 1
        ended = self.retrieved > self.polls_until_ended
        return _batch(batch_id, "ended" if ended else "in_progress")

    def results(self, batch_id: str) -> Iterator[MessageBatchIndividualResponse]:
        for r in self.results_data:
            yield MessageBatchIndividualResponse.model_validate(r)


class _Namespace:
    pass


class FakeAnthropic:
    def __init__(
        self,
        sync: list[dict[str, Any] | Exception] | None = None,
        batch_results: list[dict[str, Any]] | None = None,
        polls_until_ended: int = 0,
    ) -> None:
        self.beta = _Namespace()
        self.beta.messages = FakeBetaMessages(list(sync or []))  # type: ignore[attr-defined]
        self.messages = _Namespace()
        self.messages.batches = FakeBatches(batch_results or [], polls_until_ended)  # type: ignore[attr-defined]


def as_message(d: dict[str, Any]) -> Message:
    return Message.model_validate(d)
