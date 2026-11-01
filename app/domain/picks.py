"""Weekly email picks and send schedule (SPEC.md §10.1-10.2). Pure: `now` comes in."""

from collections.abc import Callable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.ranking import RankedPaper


@dataclass(frozen=True)
class Picks:
    fresh: RankedPaper | None = None
    missed: RankedPaper | None = None

    @property
    def quiet(self) -> bool:
        """Nothing eligible: a "quiet week" email, and the admin is alerted."""
        return self.fresh is None and self.missed is None


def select_picks(
    ranked: Sequence[RankedPaper], *, sent: AbstractSet[str], fresh_since: date, cutoff: float
) -> Picks:
    """Fresh and missed picks from eligible papers ranked best first (`rank()` output).

    Fresh: the best paper entered since `fresh_since`. Missed: the best of the rest. Each
    needs a weighted score of at least `cutoff`; if neither has one, the single best paper
    goes anyway, in the slot its date belongs to, so an email is never empty.
    """
    unsent = [r for r in ranked if r.paper.pmid not in sent]
    if not unsent:
        return Picks()
    fresh = _first(unsent, lambda r: r.paper.entrez_date >= fresh_since)
    missed = _first(unsent, lambda r: r is not fresh)
    picks = Picks(fresh=_clearing(fresh, cutoff), missed=_clearing(missed, cutoff))
    if not picks.quiet:
        return picks
    best = unsent[0]
    return Picks(fresh=best) if best is fresh else Picks(missed=best)


def _first(
    ranked: Sequence[RankedPaper], keep: Callable[[RankedPaper], bool]
) -> RankedPaper | None:
    return next((r for r in ranked if keep(r)), None)


def _clearing(pick: RankedPaper | None, cutoff: float) -> RankedPaper | None:
    """The pick if its weighted score reaches the email cutoff."""
    return pick if pick is not None and pick.weighted >= cutoff else None


def local_week(now: datetime, tz: ZoneInfo) -> date:
    """Monday of the week containing `now` in the user's timezone."""
    local = now.astimezone(tz).date()
    return local - timedelta(days=local.weekday())


def is_due(now: datetime, tz: ZoneInfo, *, weekday: int, at: time) -> bool:
    """Whether this week's send slot (weekday at local time) has passed.

    From the slot until the week ends, so a missed hourly run catches up; whether this
    week's email was already sent is checked separately.
    """
    slot = datetime.combine(local_week(now, tz) + timedelta(days=weekday), at, tzinfo=tz)
    return now >= slot
