"""LLM cost accounting (SPEC.md §6.6, §14). Re-check list prices before quoting."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import LlmSpend

BATCH_DISCOUNT = Decimal("0.5")


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: Decimal
    output: Decimal
    cache_write: Decimal  # 5-minute cache writes
    cache_read: Decimal


PRICES: dict[str, Price] = {
    "claude-sonnet-5-5": Price(
        input=Decimal("2.00"),
        output=Decimal("10.00"),
        cache_write=Decimal("2.50"),
        cache_read=Decimal("0.20"),
    ),
}


@dataclass(frozen=True)
class TokenUsage:
    input: int = 0  # uncached input
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0

    @property
    def total_input(self) -> int:
        return self.input + self.cache_write + self.cache_read

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input + other.input,
            self.output + other.output,
            self.cache_write + other.cache_write,
            self.cache_read + other.cache_read,
        )


def cost_usd(model: str, usage: TokenUsage, *, batch: bool) -> Decimal:
    """Cost of one request. Unknown models are priced at the most expensive known rate."""
    p = PRICES.get(model) or max(PRICES.values(), key=lambda x: x.output)
    usd = (
        usage.input * p.input
        + usage.output * p.output
        + usage.cache_write * p.cache_write
        + usage.cache_read * p.cache_read
    ) / Decimal(1_000_000)
    return usd * BATCH_DISCOUNT if batch else usd


def record_spend(session: Session, day: date, usd: Decimal) -> None:
    """Add `usd` to the month containing `day`. Caller commits."""
    month = day.replace(day=1)
    stmt = insert(LlmSpend).values(month=month, usd=usd)
    stmt = stmt.on_conflict_do_update(
        index_elements=[LlmSpend.month], set_={"usd": LlmSpend.usd + stmt.excluded.usd}
    )
    session.execute(stmt)
