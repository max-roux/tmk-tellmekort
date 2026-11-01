"""Anthropic grading client: one synchronous call, or a Message Batch (SPEC.md §6.5, §7).

Thin wrapper: builds requests, sends them, and turns responses into GradeOutcome or
GradeFailure. Storage and orchestration live in app.jobs.grade_papers.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from app.db.models import Paper
from app.grading.cost import TokenUsage, cost_usd
from app.grading.rubric import GRADE_SCHEMA, RUBRIC_TEXT
from app.grading.validation import GradeData, GradeValidationError, InputSource, validate_grade

MAX_TOKENS = 16_000  # thinking + answer; billed only for what is generated
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class GradeOutcome:
    pmid: str
    model: str  # the model that actually answered (may be a fallback)
    input_source: InputSource
    data: GradeData
    usage: TokenUsage
    cost: Decimal


@dataclass(frozen=True)
class GradeFailure:
    pmid: str
    reason: str
    cost: Decimal = Decimal(0)


GradeResult = GradeOutcome | GradeFailure


@dataclass(frozen=True)
class GradeInput:
    paper: Paper
    full_text: str | None = None
    # Set when parsing batch results, where the text sent is recorded but not kept.
    source: InputSource | None = None

    @property
    def input_source(self) -> InputSource:
        if self.source is not None:
            return self.source
        return "full_text" if self.full_text else "abstract"


class _Usage(Protocol):
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int | None
    cache_read_input_tokens: int | None


class _Message(Protocol):
    @property
    def model(self) -> str: ...
    @property
    def stop_reason(self) -> str | None: ...
    @property
    def content(self) -> Any: ...
    @property
    def usage(self) -> Any: ...


def build_user_content(item: GradeInput) -> str:
    p = item.paper
    lines = [
        f"Title: {p.title}",
        f"Journal: {p.journal}",
        f"Publication types: {', '.join(p.pub_types) or 'not given'}",
        f"MeSH terms: {', '.join(p.mesh_terms) or 'not yet indexed'}",
        f"Published: {p.pub_date.isoformat() if p.pub_date else 'unknown'}",
        f"Grading from: {'full text' if item.full_text else 'abstract only'}",
        "",
        f"<abstract>\n{p.abstract}\n</abstract>",
    ]
    if item.full_text:
        lines.append(f"<full_text>\n{item.full_text}\n</full_text>")
    return "\n".join(lines)


# Real rubric v1 grades used at most ~610 output tokens (thinking + answer); keep headroom.
ESTIMATED_OUTPUT_TOKENS = 800
CHARS_PER_TOKEN = 4


def estimate_cost(model: str, item: GradeInput) -> Decimal:
    """Batch cost of grading `item`, from text length, before submitting (SPEC.md §6.6).

    Ignores prompt caching, so it errs high.
    """
    chars = len(RUBRIC_TEXT) + len(build_user_content(item))
    usage = TokenUsage(input=chars // CHARS_PER_TOKEN, output=ESTIMATED_OUTPUT_TOKENS)
    return cost_usd(model, usage, batch=True)


def _usage(u: _Usage) -> TokenUsage:
    return TokenUsage(
        input=u.input_tokens,
        output=u.output_tokens,
        cache_write=u.cache_creation_input_tokens or 0,
        cache_read=u.cache_read_input_tokens or 0,
    )


def parse_message(message: _Message, item: GradeInput, *, batch: bool) -> GradeResult:
    """Turn a Messages API response into a validated grade or a failure."""
    pmid = item.paper.pmid
    usage = _usage(message.usage)
    cost = cost_usd(message.model, usage, batch=batch)
    if message.stop_reason == "refusal":
        return GradeFailure(pmid, "refused", cost)
    if message.stop_reason == "max_tokens":
        return GradeFailure(pmid, "hit max_tokens", cost)
    text = next((b.text for b in message.content if b.type == "text"), None)
    if text is None:
        return GradeFailure(pmid, f"no text block (stop_reason={message.stop_reason})", cost)
    try:
        data = validate_grade(json.loads(text), item.input_source)
    except (json.JSONDecodeError, GradeValidationError) as e:
        return GradeFailure(pmid, f"invalid grade: {e}", cost)
    return GradeOutcome(pmid, message.model, item.input_source, data, usage, cost)


class Grader:
    def __init__(
        self, client: anthropic.Anthropic, *, model: str, effort: str, max_tokens: int = MAX_TOKENS
    ) -> None:
        self._client = client
        self.model = model
        self._effort = effort
        self._max_tokens = max_tokens

    def request_params(self, item: GradeInput) -> MessageCreateParamsNonStreaming:
        return {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": [
                {"type": "text", "text": RUBRIC_TEXT, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": "user", "content": build_user_content(item)}],
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": self._effort,  # type: ignore[typeddict-item]
                "format": {"type": "json_schema", "schema": GRADE_SCHEMA},
            },
        }

    def grade_sync(self, item: GradeInput) -> GradeResult:
        """One synchronous call, with server-side fallback if the model declines."""
        try:
            message = self._client.beta.messages.create(
                **self.request_params(item),  # type: ignore[arg-type]
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIStatusError as e:
            return GradeFailure(item.paper.pmid, f"API error {e.status_code}: {e.message}")
        except anthropic.APIConnectionError as e:
            return GradeFailure(item.paper.pmid, f"connection error: {e}")
        return parse_message(message, item, batch=False)

    def submit_batch(self, items: Iterable[GradeInput]) -> str:
        requests = [Request(custom_id=i.paper.pmid, params=self.request_params(i)) for i in items]
        return self._client.messages.batches.create(requests=requests).id

    def batch_ended(self, batch_id: str) -> bool:
        return self._client.messages.batches.retrieve(batch_id).processing_status == "ended"

    def batch_results(self, batch_id: str, items: dict[str, GradeInput]) -> list[GradeResult]:
        """Results keyed by custom_id (= PMID); they arrive in any order."""
        results: list[GradeResult] = []
        for r in self._client.messages.batches.results(batch_id):
            item = items.get(r.custom_id)
            if item is None:
                continue
            if r.result.type == "succeeded":
                results.append(parse_message(r.result.message, item, batch=True))
            elif r.result.type == "errored":
                results.append(GradeFailure(r.custom_id, f"errored: {r.result.error.error.type}"))
            else:
                results.append(GradeFailure(r.custom_id, r.result.type))
        return results
