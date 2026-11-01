"""Onboarding topic extraction (SPEC.md §11.1): free text -> 4-12 topic chips.

One synchronous Sonnet call with JSON-schema output (forced tool use is not available
on this model). The surgeon confirms or edits the proposals before anything is saved.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import anthropic
from anthropic.types import OutputConfigParam

from app.grading.cost import TokenUsage, cost_usd

MAX_INTEREST_CHARS = 4_000
MAX_TOPICS = 12

SYSTEM = """\
You help a maxillofacial surgeon set up a weekly feed of research papers from PubMed.
They describe their clinical and research interests in their own words. Turn that into
4 to 12 topics that together cover everything they mention, without overlap.

For each topic give:
- label: a short chip, at most 8 words, e.g. "Orthognathic surgery: virtual surgical
  planning".
- description: 1-2 sentences in PubMed vocabulary (MeSH terms, procedure and condition
  names, study populations) describing the papers that belong to this topic. It is used
  for semantic matching against titles and abstracts, so be concrete; no filler like
  "this topic covers".

Stay within what they wrote: split broad interests into distinct topics, but do not
invent interests they did not mention. Ignore anything that is not a research interest.
Write in English even if they write in another language.
"""

TOPICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["label", "description"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["topics"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ProposedTopic:
    label: str
    description: str


@dataclass(frozen=True)
class Proposal:
    topics: list[ProposedTopic]
    cost: Decimal


class TopicProposalError(Exception):
    pass


def parse_topics(raw: str) -> list[ProposedTopic]:
    try:
        data = json.loads(raw)
        items = data["topics"]
        topics = [
            ProposedTopic(" ".join(t["label"].split()), " ".join(t["description"].split()))
            for t in items
        ]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        raise TopicProposalError(f"unexpected output: {e}") from e
    topics = [t for t in topics if t.label]
    if not topics:
        raise TopicProposalError("no topics proposed")
    return topics[:MAX_TOPICS]


class TopicProposer:
    def __init__(
        self,
        client: anthropic.Anthropic,
        *,
        model: str,
        effort: str = "low",
        max_tokens: int = 8_000,
    ) -> None:
        self._client = client
        self.model = model
        self._effort = effort
        self._max_tokens = max_tokens

    def propose(self, interests: str) -> Proposal:
        text = interests.strip()[:MAX_INTEREST_CHARS]
        output_config: OutputConfigParam = {
            "effort": self._effort,  # type: ignore[typeddict-item]
            "format": {"type": "json_schema", "schema": TOPICS_SCHEMA},
        }
        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=SYSTEM,
                messages=[{"role": "user", "content": f"<interests>\n{text}\n</interests>"}],
                thinking={"type": "adaptive"},
                output_config=output_config,
            )
        except anthropic.APIError as e:
            raise TopicProposalError(f"API error: {e}") from e
        u = message.usage
        usage = TokenUsage(
            input=u.input_tokens,
            output=u.output_tokens,
            cache_write=u.cache_creation_input_tokens or 0,
            cache_read=u.cache_read_input_tokens or 0,
        )
        cost = cost_usd(message.model, usage, batch=False)
        if message.stop_reason != "end_turn":
            raise TopicProposalError(f"stopped early: {message.stop_reason}")
        raw = "".join(b.text for b in message.content if b.type == "text")
        return Proposal(parse_topics(raw), cost)
