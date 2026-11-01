"""The front page's edition line (SPEC.md §11.2). Pure: `now` comes in."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.domain.picks import local_week


@dataclass(frozen=True)
class Edition:
    number: int  # ISO week number
    week_of: date  # Monday of that week, in the reader's timezone
    papers: int

    @property
    def week_label(self) -> str:
        """'26 October 2026', without a zero-padded day."""
        return f"{self.week_of.day} {self.week_of:%B %Y}"


def edition(now: datetime, tz: ZoneInfo, papers: int) -> Edition:
    """This week's edition for a reader in `tz`, carrying `papers` papers."""
    monday = local_week(now, tz)
    return Edition(number=monday.isocalendar().week, week_of=monday, papers=papers)
