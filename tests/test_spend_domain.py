from decimal import Decimal as D

from app.domain.spend import crossed_alert_line, fit_budget


def test_everything_fits_under_the_cap() -> None:
    b = fit_budget([("a", D("1")), ("b", D("2"))], spent=D("10"), cap=D("30"))
    assert (b.kept, b.dropped, b.estimate) == (["a", "b"], [], D("3"))
    assert not b.truncated


def test_keeps_the_top_n_that_fit_in_priority_order() -> None:
    # 27 spent, cap 30: room for 3. "a" (1) and "b" (1.5) fit; "c" (1) would fit after the
    # first refusal, but only a prefix is kept so higher priority always wins.
    b = fit_budget(
        [("a", D("1")), ("b", D("1.5")), ("big", D("2")), ("c", D("0.4"))],
        spent=D("27"),
        cap=D("30"),
    )
    assert (b.kept, b.dropped, b.estimate) == (["a", "b"], ["big", "c"], D("2.5"))
    assert b.truncated


def test_nothing_fits_once_the_cap_is_reached() -> None:
    b = fit_budget([("a", D("0.01"))], spent=D("30"), cap=D("30"))
    assert (b.kept, b.dropped) == ([], ["a"])


def test_alert_when_spend_crosses_80_percent_once() -> None:
    assert crossed_alert_line(D("20"), D("24"), D("30"))  # 24 = 80%
    assert not crossed_alert_line(D("24"), D("25"), D("30"))  # already over: no repeat
    assert not crossed_alert_line(D("10"), D("23.99"), D("30"))
