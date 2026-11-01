"""Weight suggestions from likes (SPEC.md §8.5). Pure; weights never change silently."""

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from statistics import fmean

from app.domain.criteria import ALL_CRITERIA
from app.domain.preferences import WEIGHT_MAX

MIN_LIKES = 10
MIN_GAP = 0.75

Scores = Mapping[str, int]


def suggest_weight(
    liked: Sequence[Scores],
    others: Sequence[Scores],
    weights: Mapping[str, float],
    dismissed: AbstractSet[str],
) -> str | None:
    """The criterion liked papers beat shown-but-not-liked ones on by the widest margin
    (at least MIN_GAP), unless it already has the sole highest weight, cannot go higher,
    or the user dismissed it.
    """
    if len(liked) < MIN_LIKES or not others:
        return None
    gaps = {c: fmean(s[c] for s in liked) - fmean(s[c] for s in others) for c in ALL_CRITERIA}
    candidates = [
        c
        for c in ALL_CRITERIA
        if gaps[c] >= MIN_GAP and _can_raise(c, weights) and c not in dismissed
    ]
    return max(candidates, key=lambda c: gaps[c], default=None)


def _can_raise(c: str, weights: Mapping[str, float]) -> bool:
    """Below the maximum, and some other criterion weighs at least as much."""
    others = [w for k, w in weights.items() if k != c]
    return weights[c] < WEIGHT_MAX and max(others) >= weights[c]


def raised_weight(weights: Mapping[str, float]) -> float:
    """What applying a suggestion sets the weight to: one above the highest, at most 5."""
    return min(WEIGHT_MAX, max(weights.values()) + 1)
