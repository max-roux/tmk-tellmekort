from decimal import Decimal

import anthropic
import httpx
import pytest

from app.profiles.topics import MAX_TOPICS, TopicProposalError, TopicProposer, parse_topics
from tests.fakes import FakeMessagesClient, message


def proposer(*responses: object) -> tuple[TopicProposer, FakeMessagesClient]:
    client = FakeMessagesClient(list(responses))  # type: ignore[arg-type]
    return TopicProposer(client, model="claude-sonnet-5-5"), client  # type: ignore[arg-type]


def test_propose_parses_topics_and_prices_the_call() -> None:
    p, client = proposer(message("message_topics.json"))
    proposal = p.propose("  Orthognathic VSP, fibula flaps, MRONJ, TMJ replacement  ")
    labels = [t.label for t in proposal.topics]
    assert labels[1] == "Mandibular reconstruction with fibula flap"  # whitespace collapsed
    assert len(labels) == 4
    assert proposal.cost == Decimal("0.004640")  # 420 x $2 + 380 x $10 per M

    call = client.messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in call and "tools" not in call
    assert call["messages"][0]["content"].startswith("<interests>\nOrthognathic VSP")


def test_long_interests_are_truncated() -> None:
    p, client = proposer(message("message_topics.json"))
    p.propose("x" * 10_000)
    assert len(client.messages.calls[0]["messages"][0]["content"]) < 4_100


def test_stopped_early_or_api_error_raise() -> None:
    p, _ = proposer(message("message_topics.json", stop_reason="max_tokens"))
    with pytest.raises(TopicProposalError, match="max_tokens"):
        p.propose("anything")
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.APIConnectionError(request=req)
    p, _ = proposer(err)
    with pytest.raises(TopicProposalError):
        p.propose("anything")


def test_parse_topics_rejects_bad_output_and_caps_count() -> None:
    with pytest.raises(TopicProposalError):
        parse_topics("not json")
    with pytest.raises(TopicProposalError):
        parse_topics('{"topics": []}')
    many = '{"topics": [' + ",".join(['{"label": "t", "description": "d"}'] * 20) + "]}"
    assert len(parse_topics(many)) == MAX_TOPICS
