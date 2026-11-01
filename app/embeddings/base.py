"""Embedding provider interface, so Voyage can be swapped (SPEC.md §3)."""

from dataclasses import dataclass
from typing import Literal, Protocol

InputType = Literal["document", "query"]


@dataclass(frozen=True)
class Embeddings:
    vectors: list[list[float]]
    tokens: int


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    def embed(self, texts: list[str], input_type: InputType) -> Embeddings:
        """One vector per text, in input order."""
        ...


def paper_text(title: str, abstract: str) -> str:
    """What gets embedded for a paper: title + abstract (SPEC.md §5)."""
    return f"{title}\n\n{abstract}"
