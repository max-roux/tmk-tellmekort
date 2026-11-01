"""LLM spend guard (SPEC.md §6.6). Pure."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

ALERT_SHARE = Decimal("0.8")


@dataclass(frozen=True)
class Budget:
    kept: list[str]
    dropped: list[str]
    estimate: Decimal  # estimated cost of the kept papers

    @property
    def truncated(self) -> bool:
        return bool(self.dropped)


def fit_budget(estimates: Sequence[tuple[str, Decimal]], *, spent: Decimal, cap: Decimal) -> Budget:
    """The longest prefix of `estimates` (PMID, estimated USD; best first) that fits under
    `cap` given what the month has `spent`. Stopping at the first paper that does not fit
    keeps priority strict: a cheaper, lower-ranked paper never displaces a better one.
    """
    total = Decimal(0)
    for i, (_, usd) in enumerate(estimates):
        if spent + total + usd > cap:
            return Budget([p for p, _ in estimates[:i]], [p for p, _ in estimates[i:]], total)
        total += usd
    return Budget([p for p, _ in estimates], [], total)


def crossed_alert_line(before: Decimal, after: Decimal, cap: Decimal) -> bool:
    """True when spend went from under 80% of the cap to at or over it."""
    line = cap * ALERT_SHARE
    return before < line <= after
