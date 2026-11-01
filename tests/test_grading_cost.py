from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.models import LlmSpend
from app.grading.cost import TokenUsage, cost_usd, record_spend


def test_sonnet_cost_standard_and_batch() -> None:
    usage = TokenUsage(input=1_000_000, output=100_000, cache_write=0, cache_read=1_000_000)
    # $2 input + $1 output + $0.20 cache read
    assert cost_usd("claude-sonnet-5-5", usage, batch=False) == Decimal("3.2")
    assert cost_usd("claude-sonnet-5-5", usage, batch=True) == Decimal("1.6")


def test_spec_envelope_per_paper() -> None:
    # SPEC §14 basis: ~6.4k input + ~600 output tokens, batch pricing.
    per_paper = cost_usd("claude-sonnet-5-5", TokenUsage(input=6_400, output=600), batch=True)
    assert per_paper == Decimal("0.0094")


def test_unknown_model_priced_at_most_expensive_known_rate() -> None:
    u = TokenUsage(output=1_000_000)
    assert cost_usd("some-fallback-model", u, batch=False) == Decimal("10")


def test_total_input_and_addition() -> None:
    a = TokenUsage(input=1, output=2, cache_write=3, cache_read=4)
    assert a.total_input == 8
    assert (a + a).output == 4


@pytest.mark.db
def test_record_spend_accumulates_per_month(db_session: Session) -> None:
    from datetime import date

    record_spend(db_session, date(2026, 11, 3), Decimal("1.25"))
    record_spend(db_session, date(2026, 11, 28), Decimal("0.75"))
    record_spend(db_session, date(2026, 12, 1), Decimal("0.10"))
    db_session.commit()
    assert db_session.get(LlmSpend, date(2026, 11, 1)).usd == Decimal("2.000000")
    assert db_session.get(LlmSpend, date(2026, 12, 1)).usd == Decimal("0.100000")
