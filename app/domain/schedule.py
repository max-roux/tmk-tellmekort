"""Parse a user's weekly-email schedule from a form (SPEC.md §10.1, §11 /settings). Pure."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Schedule:
    weekday: int  # 0 = Monday
    at: time
    timezone: str


class ScheduleError(ValueError):
    pass


def parse_schedule(form: Mapping[str, str]) -> Schedule:
    weekday = form.get("send_weekday", "")
    if not weekday.isdigit() or not 0 <= int(weekday) <= 6:
        raise ScheduleError("Pick a day of the week.")
    try:
        at = time.fromisoformat(form.get("send_local_time", ""))
    except ValueError:
        raise ScheduleError("Give the time as HH:MM.") from None
    tz = form.get("timezone", "")
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleError(f"Unknown timezone {tz!r}.") from None
    return Schedule(int(weekday), at.replace(second=0, microsecond=0), tz)
