from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.domain.edition import edition

CPH = ZoneInfo("Europe/Copenhagen")


def test_edition_is_the_iso_week_of_the_readers_monday() -> None:
    e = edition(datetime(2026, 10, 29, 9, tzinfo=UTC), CPH, 10)
    assert (e.number, e.week_of, e.papers) == (44, date(2026, 10, 26), 10)
    assert e.week_label == "26 October 2026"


def test_edition_follows_the_readers_timezone_across_midnight() -> None:
    # Sunday 23:30 UTC is already Monday in Copenhagen: the next edition.
    e = edition(datetime(2026, 11, 1, 23, 30, tzinfo=UTC), CPH, 0)
    assert (e.number, e.week_of) == (45, date(2026, 11, 2))
    assert edition(datetime(2026, 11, 1, 23, 30, tzinfo=UTC), ZoneInfo("UTC"), 0).number == 44


def test_week_label_has_no_zero_padding() -> None:
    assert edition(datetime(2026, 1, 7, tzinfo=UTC), CPH, 1).week_label == "5 January 2026"
