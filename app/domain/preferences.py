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


class PreferencesError(ValueError):
    pass


def parse_preferences(form: Mapping[str, str]) -> Preferences:
    """Read w_<criterion> (0-5), min_<criterion> (blank or 1-5) and hide_case_reports.

    Raises PreferencesError with a message for the surgeon; at least one weight must be
    above zero, or nothing could be ranked.
    """
    weights: dict[str, float] = {}
    minimums: dict[str, int | None] = {}
    for c in ALL_CRITERIA:
        label = c.replace("_", " ")
        try:
            w = float(form.get(f"w_{c}", "1") or "0")
        except ValueError:
            raise PreferencesError(f"The weight for {label} must be a number.") from None
        if not 0 <= w <= WEIGHT_MAX:
            raise PreferencesError(f"The weight for {label} must be between 0 and 5.")
        weights[c] = w
        raw_min = (form.get(f"min_{c}") or "").strip()
        if raw_min and (not raw_min.isdigit() or not 1 <= int(raw_min) <= 5):
            raise PreferencesError(f"The minimum for {label} must be 1 to 5, or none.")
        minimums[c] = int(raw_min) if raw_min else None
    if not any(weights.values()):
        raise PreferencesError("Give at least one criterion a weight above zero.")
    return Preferences(weights, minimums, form.get("hide_case_reports") in ("on", "true", "1"))
