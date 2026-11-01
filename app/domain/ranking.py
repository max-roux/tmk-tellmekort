"""Per-user pertinence and ranking (SPEC.md §8). Pure.

Milestone 6 adds the profile vector (§8.1); pertinence, eligibility and the weighted
score follow in milestone 7.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

Vectors = Sequence[Sequence[float]]


@dataclass(frozen=True)
class ProfileCoefficients:
    topics: float = 1.0
    seeds: float = 1.0
    liked: float = 0.5
    not_for_me: float = 0.3  # subtracted


def _mean(vectors: Vectors) -> np.ndarray | None:
    if not vectors:
        return None
    return np.asarray(vectors, dtype=np.float64).mean(axis=0)


def profile_vector(
    *,
    topics: Vectors,
    seeds: Vectors = (),
    liked: Vectors = (),
    not_for_me: Vectors = (),
    coefficients: ProfileCoefficients = ProfileCoefficients(),  # noqa: B008 (frozen)
) -> list[float] | None:
    """normalize(a·mean(topics) + b·mean(seeds) + c·mean(liked) - d·mean(not_for_me)).

    Missing groups drop out. None when there is nothing positive to build from, or the
    terms cancel out.
    """
    terms = [
        (coefficients.topics, _mean(topics)),
        (coefficients.seeds, _mean(seeds)),
        (coefficients.liked, _mean(liked)),
    ]
    positives = [w * m for w, m in terms if m is not None]
    if not positives:
        return None
    v = np.sum(positives, axis=0)
    if (neg := _mean(not_for_me)) is not None:
        v = v - coefficients.not_for_me * neg
    norm = float(np.linalg.norm(v))
    if norm == 0.0:
        return None
    return [float(x) for x in v / norm]
