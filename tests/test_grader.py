from datetime import date
from decimal import Decimal

import anthropic
import httpx
import pytest

from app.db.models import Paper
from app.grading.grader import (
    ESTIMATED_OUTPUT_TOKENS,
    FALLBACK_BETA,
    GradeFailure,
    GradeInput,
    GradeOutcome,
    Grader,
    build_user_content,
    estimate_cost,
    parse_message,
)
from app.grading.rubric import GRADE_SCHEMA, RUBRIC_TEXT
from tests.fakes import FakeAnthropic, as_message, batch_lines, message


def paper(pmid: str = "42958619") -> Paper:
    return Paper(
        pmid=pmid,
        title="Grafting small dehiscences",
        abstract="OBJECTIVE: compare grafts.\nRESULTS: no difference.",
        journal="Clin Implant Dent",
        pub_types=["Journal Article", "Randomized Controlled Trial"],
        mesh_terms=["Dental Implants"],
        authors=[],
        entrez_date=date(2026, 10, 30),
        pub_date=date(2026, 12, 1),
    )


def grader(fake: FakeAnthropic) -> Grader:
    return Grader(fake, model="claude-sonnet-5-5", effort="low")  # type: ignore[arg-type]


def test_request_params_follow_spec() -> None:
    params = grader(FakeAnthropic()).request_params(GradeInput(paper()))
    assert params["model"] == "claude-sonnet-5-5"
    assert "temperature" not in params  # rejected by the API since 2026-10-21
    assert "tools" not in params and "tool_choice" not in params
    assert params["system"] == [
        {"type": "text", "text": RUBRIC_TEXT, "cache_control": {"type": "ephemeral"}}
    ]
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": GRADE_SCHEMA},
    }


def test_user_content_has_metadata_and_abstract() -> None:
    text = build_user_content(GradeInput(paper()))
    assert "Title: Grafting small dehiscences" in text
    assert "Publication types: Journal Article, Randomized Controlled Trial" in text
    assert "Grading from: abstract only" in text
    assert "<abstract>\nOBJECTIVE: compare grafts." in text
    assert "<full_text>" not in text
    full = build_user_content(GradeInput(paper(), full_text="METHODS ..."))
    assert "<full_text>\nMETHODS ...\n</full_text>" in full
    assert "Grading from: full text" in full


def test_parse_ok_message_from_abstract_clamps_depth() -> None:
    r = parse_message(as_message(message()), GradeInput(paper()), batch=True)
    assert isinstance(r, GradeOutcome)
    assert r.input_source == "abstract"
    assert r.data.scores["depth"] == 4
    assert r.usage.total_input == 2310 + 1180
    # batch: (2310*2 + 612*10 + 1180*0.2) / 1e6 / 2
    assert r.cost == Decimal("0.005488")


def test_parse_refusal_and_max_tokens_and_bad_json() -> None:
    item = GradeInput(paper())
    refused = parse_message(as_message(message("message_refusal.json")), item, batch=False)
    assert isinstance(refused, GradeFailure) and refused.reason == "refused"
    assert refused.cost > 0  # input tokens are still billed

    truncated = parse_message(as_message(message(stop_reason="max_tokens")), item, batch=False)
    assert isinstance(truncated, GradeFailure) and "max_tokens" in truncated.reason

    garbled = message(content=[{"type": "text", "text": "{not json"}])
    r = parse_message(as_message(garbled), item, batch=False)
    assert isinstance(r, GradeFailure) and r.reason.startswith("invalid grade")


def test_grade_sync_uses_server_side_fallback_and_records_answering_model() -> None:
    fake = FakeAnthropic(sync=[message(model="claude-opus-4-8")])
    r = grader(fake).grade_sync(GradeInput(paper()))
    call = fake.beta.messages.calls[0]  # type: ignore[attr-defined]
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"
    assert isinstance(r, GradeOutcome) and r.model == "claude-opus-4-8"


def test_grade_sync_api_error_becomes_failure() -> None:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.InternalServerError(
        "boom", response=httpx.Response(500, request=req), body=None
    )
    r = grader(FakeAnthropic(sync=[err])).grade_sync(GradeInput(paper()))
    assert isinstance(r, GradeFailure) and "500" in r.reason


def test_batch_submit_and_results_by_custom_id() -> None:
    lines = batch_lines()
    fake = FakeAnthropic(batch_results=[*lines, {**lines[3], "custom_id": "unknown"}])
    g = grader(fake)
    pmids = ["42958619", "42963182", "42949936", "42963307"]
    items = {p: GradeInput(paper(p)) for p in pmids}

    batch_id = g.submit_batch(items.values())
    requests = fake.messages.batches.created[0]  # type: ignore[attr-defined]
    assert [r["custom_id"] for r in requests] == pmids
    assert g.batch_ended(batch_id)

    results = {r.pmid: r for r in g.batch_results(batch_id, items)}
    assert set(results) == set(pmids)  # unknown custom_id ignored
    assert isinstance(results["42958619"], GradeOutcome)
    assert "invalid grade" in results["42963182"].reason  # type: ignore[union-attr]
    assert results["42949936"].reason == "errored: overloaded_error"  # type: ignore[union-attr]
    assert results["42963307"].reason == "expired"  # type: ignore[union-attr]


def test_parses_recorded_live_response() -> None:
    """A real claude-sonnet-5-5 response (2026-11-01), structured output + low effort."""
    recorded = message("message_grade_recorded.json")
    r = parse_message(as_message(recorded), GradeInput(paper("42963182")), batch=False)
    assert isinstance(r, GradeOutcome), r
    assert r.model == "claude-sonnet-5-5"
    assert all(1 <= s <= 5 for s in r.data.scores.values())
    assert r.usage.cache_read > 0  # rubric system prompt served from cache


def test_estimate_cost_is_batch_priced_and_grows_with_full_text() -> None:
    abstract = estimate_cost("claude-sonnet-5-5", GradeInput(paper()))
    chars = len(RUBRIC_TEXT) + len(build_user_content(GradeInput(paper())))
    # Batch: $1 / $5 per million input / output tokens.
    expected = (Decimal(chars // 4) * 1 + Decimal(ESTIMATED_OUTPUT_TOKENS) * 5) / 1_000_000
    assert abstract == expected
    full = estimate_cost("claude-sonnet-5-5", GradeInput(paper(), "x" * 40_000))
    # 40,000 chars = 10,000 more input tokens (plus the <full_text> tags) at $1 per million.
    assert Decimal("0.0100") <= full - abstract < Decimal("0.0101")


def test_batch_status_errors_mean_not_ended_yet_so_the_wait_goes_on() -> None:
    fake = FakeAnthropic(batch_results=batch_lines())
    request = httpx.Request("GET", "https://api.anthropic.com/v1/messages/batches/b")
    outage = [
        anthropic.APIConnectionError(request=request),
        anthropic.InternalServerError(
            "down", response=httpx.Response(503, request=request), body=None
        ),
    ]
    original = fake.messages.batches.retrieve  # type: ignore[attr-defined]

    def flaky(batch_id: str):  # type: ignore[no-untyped-def]
        if outage:
            raise outage.pop(0)
        return original(batch_id)

    fake.messages.batches.retrieve = flaky  # type: ignore[attr-defined]
    g = grader(fake)
    assert not g.batch_ended("b") and not g.batch_ended("b")
    assert g.batch_ended("b")


def test_batch_status_client_errors_still_raise() -> None:
    fake = FakeAnthropic()
    request = httpx.Request("GET", "https://api.anthropic.com/v1/messages/batches/b")

    def missing(batch_id: str):  # type: ignore[no-untyped-def]
        raise anthropic.NotFoundError(
            "no such batch", response=httpx.Response(404, request=request), body=None
        )

    fake.messages.batches.retrieve = missing  # type: ignore[attr-defined]
    with pytest.raises(anthropic.NotFoundError):
        grader(fake).batch_ended("b")
