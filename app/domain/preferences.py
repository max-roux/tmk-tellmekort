"""Criterion weights, minimums and hard filters from a form (SPEC.md §5, §11). Pure."""

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.criteria import ALL_CRITERIA

WEIGHT_MAX = 5.0


@dataclass(frozen=True)
class Preferences:
    weights: dict[str, float]
    minimums: dict[str, int | None]
    hide_case_reports: bool
    study_types: frozenset[str] | None = None  # design buckets to keep; None keeps all


class PreferencesError(ValueError):
    pass


def _weight(form: Mapping[str, str], c: str) -> float:
    label = c.replace("_", " ")
    try:
        w = float(form.get(f"w_{c}", "1") or "0")
    except ValueError:
        raise PreferencesError(f"The weight for {label} must be a number.") from None
    if not 0 <= w <= WEIGHT_MAX:
        raise PreferencesError(f"The weight for {label} must be between 0 and 5.")
    return w


def _minimum(form: Mapping[str, str], c: str) -> int | None:
    raw = (form.get(f"min_{c}") or "").strip()
    if not raw:
        return None
    if not raw.isdigit() or not 1 <= int(raw) <= 5:
        raise PreferencesError(f"The minimum for {c.replace('_', ' ')} must be 1 to 5, or none.")
    return int(raw)


def parse_preferences(form: Mapping[str, str]) -> Preferences:
    """Read w_<criterion> (0-5), min_<criterion> (blank or 1-5) and hide_case_reports.

    Raises PreferencesError with a message for the surgeon; at least one weight must be
    above zero, or nothing could be ranked.
    """
    weights = {c: _weight(form, c) for c in ALL_CRITERIA}
    minimums = {c: _minimum(form, c) for c in ALL_CRITERIA}
    if not any(weights.values()):
        raise PreferencesError("Give at least one criterion a weight above zero.")
    return Preferences(weights, minimums, form.get("hide_case_reports") in ("on", "true", "1"))
