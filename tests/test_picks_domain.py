from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.domain.picks import Picks, due_slot, local_week, select_picks
from app.domain.ranking import GradedPaper, RankedPaper

FRESH_SINCE = date(2026, 10, 26)
OLD, NEW = date(2026, 9, 1), date(2026, 10, 30)
CPH = ZoneInfo("Europe/Copenhagen")


def ranked(pmid: str, weighted: float, entrez: date) -> RankedPaper:
    paper = GradedPaper(pmid, {}, 0.5, entrez, ())
    return RankedPaper(paper, 3, weighted)


def picks(*items: RankedPaper, sent: frozenset[str] = frozenset()) -> tuple[str | None, str | None]:
    p = select_picks(list(items), sent=sent, fresh_since=FRESH_SINCE, cutoff=3.5)
    return (p.fresh.paper.pmid if p.fresh else None, p.missed.paper.pmid if p.missed else None)


def test_fresh_is_best_recent_and_missed_is_best_of_the_rest() -> None:
    # Input is eligible papers, best first, as rank() returns them.
    assert picks(ranked("old1", 4.5, OLD), ranked("new1", 4.0, NEW), ranked("new2", 3.9, NEW)) == (
        "new1",
        "old1",
    )
    # The missed pick may also be recent: it is the best paper left after the fresh one.
    assert picks(ranked("new1", 4.5, NEW), ranked("new2", 4.2, NEW)) == ("new1", "new2")


def test_previously_sent_papers_are_skipped() -> None:
    items = (ranked("new1", 4.5, NEW), ranked("old1", 4.2, OLD), ranked("old2", 4.0, OLD))
    assert picks(*items, sent=frozenset({"new1", "old1"})) == (None, "old2")


def test_cutoff_drops_weak_picks_but_never_zero() -> None:
    assert picks(ranked("new1", 3.0, NEW), ranked("old1", 4.0, OLD)) == (None, "old1")
    # Neither clears 3.5: send the single best anyway, in the slot its date belongs to.
    assert picks(ranked("old1", 3.2, OLD), ranked("new1", 3.0, NEW)) == (None, "old1")
    assert picks(ranked("new1", 3.2, NEW), ranked("old1", 3.0, OLD)) == ("new1", None)


def test_nothing_eligible_is_a_quiet_week() -> None:
    assert select_picks([], sent=frozenset(), fresh_since=FRESH_SINCE, cutoff=3.5) == Picks()
    assert Picks().quiet and not Picks(fresh=ranked("a", 4, NEW)).quiet


def test_local_week_is_monday_in_the_users_timezone() -> None:
    # Sunday 23:30 UTC is already Monday 00:30 in Copenhagen (winter, UTC+1).
    assert local_week(datetime(2026, 11, 1, 23, 30, tzinfo=UTC), CPH) == date(2026, 11, 2)
    assert local_week(datetime(2026, 11, 1, 22, 30, tzinfo=UTC), CPH) == date(2026, 10, 26)


@pytest.mark.parametrize(
    ("now", "due"),
    [
        (datetime(2026, 11, 2, 5, 29, tzinfo=UTC), False),  # Monday 06:29 local
        (datetime(2026, 11, 2, 5, 30, tzinfo=UTC), True),  # Monday 06:30 local
        (datetime(2026, 11, 4, 12, 0, tzinfo=UTC), True),  # missed runs catch up later
        (datetime(2026, 11, 1, 12, 0, tzinfo=UTC), True),  # Sunday: last Monday's slot passed
    ],
)
def test_due_from_the_weekly_slot_onwards(now: datetime, due: bool) -> None:
    assert (due_slot(now, CPH, weekday=0, at=time(6, 30)) is not None) is due


def test_due_respects_summer_time() -> None:
    # Copenhagen is UTC+2 in summer: 06:30 local is 04:30 UTC.
    assert due_slot(datetime(2026, 6, 1, 4, 29, tzinfo=UTC), CPH, weekday=0, at=time(6, 30)) is None
    slot = due_slot(datetime(2026, 6, 1, 4, 30, tzinfo=UTC), CPH, weekday=0, at=time(6, 30))
    assert slot == datetime(2026, 6, 1, 6, 30, tzinfo=CPH)


def test_a_late_sunday_slot_is_still_due_after_the_week_rolls_over() -> None:
    # Sunday 23:30 Copenhagen; the hourly run at :05 comes next at Monday 00:05 local.
    monday_0005 = datetime(2026, 11, 1, 23, 5, tzinfo=UTC)
    slot = due_slot(monday_0005, CPH, weekday=6, at=time(23, 30))
    assert slot == datetime(2026, 11, 1, 23, 30, tzinfo=CPH)
    assert local_week(slot, CPH) == date(2026, 10, 26)  # the email is last week's
    # Days later, last week's slot is no longer due (only this week's, when it comes).
    assert due_slot(datetime(2026, 11, 4, 12, tzinfo=UTC), CPH, weekday=6, at=time(23, 30)) is None
