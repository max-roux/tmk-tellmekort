"""Per-user pertinence and ranking (SPEC.md §8, §9). Pure."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from app.domain.calibration import design_bucket
from app.domain.criteria import ALL_CRITERIA
from app.domain.narrowing import narrow_scores
from app.domain.preferences import Preferences

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


# --------------------------------------------------------------------------- state (§9)

# Each event sets one flag; the last event touching a flag wins.
_EVENT_EFFECT: dict[str, tuple[str, bool]] = {
    "read": ("read", True),
    "unread": ("read", False),
    "like": ("liked", True),
    "unlike": ("liked", False),
    "not_for_me": ("dismissed", True),
    "undismiss": ("dismissed", False),
}


@dataclass(frozen=True)
class PaperState:
    read: bool = False
    liked: bool = False
    dismissed: bool = False


def derive_state(kinds: Iterable[str]) -> PaperState:
    """A paper's state for one user from its feedback events, oldest first."""
    flags = {"read": False, "liked": False, "dismissed": False}
    for kind in kinds:
        flag, value = _EVENT_EFFECT[kind]
        flags[flag] = value
    return PaperState(**flags)


# --------------------------------------------------------------------------- pertinence (§8.2)


def pertinence_cosines(
    papers: Mapping[str, Sequence[float]], *, profile: Sequence[float], topics: Vectors
) -> dict[str, float]:
    """max(cos to profile, cos to the closest single topic), so a niche topic isn't diluted."""
    return narrow_scores(papers, [profile, *topics])


def pertinence_score(cos: float, thresholds: Sequence[float]) -> int:
    """1, plus one for each threshold reached: [0.30, 0.40, 0.50, 0.60] maps to 1-5."""
    return 1 + sum(cos >= t for t in thresholds)


# --------------------------------------------------------------------------- ranking (§8.3-8.4)


@dataclass(frozen=True)
class GradedPaper:
    """A paper with a current grade, as one user sees it."""

    pmid: str
    scores: Mapping[str, int]  # the four intrinsic criteria, 1-5
    pertinence_cos: float
    entrez_date: date
    pub_types: tuple[str, ...]
    state: PaperState = field(default_factory=PaperState)


@dataclass(frozen=True)
class RankingRules:
    preferences: Preferences
    gate: float  # PERTINENCE_GATE
    thresholds: tuple[float, ...]  # pertinence cosine thresholds for scores 2-5


@dataclass(frozen=True)
class RankedPaper:
    paper: GradedPaper
    pertinence: int
    weighted: float

    @property
    def scores(self) -> dict[str, int]:
        """All five criteria, pertinence first."""
        return {"pertinence": self.pertinence, **self.paper.scores}


def weighted_score(scores: Mapping[str, int], weights: Mapping[str, float]) -> float:
    """sum(w_c * s_c) / sum(w_c) over the five criteria."""
    return sum(weights[c] * scores[c] for c in ALL_CRITERIA) / sum(weights[c] for c in ALL_CRITERIA)


def _passes_filters(paper: GradedPaper, prefs: Preferences) -> bool:
    bucket = design_bucket(paper.pub_types)
    if prefs.hide_case_reports and bucket == "case report":
        return False
    return prefs.study_types is None or bucket in prefs.study_types


def _meets_minimums(scores: Mapping[str, int], minimums: Mapping[str, int | None]) -> bool:
    return all(m is None or scores[c] >= m for c, m in minimums.items())


def score_paper(paper: GradedPaper, rules: RankingRules) -> RankedPaper:
    """The five scores and weighted score, whether or not the paper is eligible."""
    pertinence = pertinence_score(paper.pertinence_cos, rules.thresholds)
    scores = {"pertinence": pertinence, **paper.scores}
    return RankedPaper(paper, pertinence, weighted_score(scores, rules.preferences.weights))


def is_eligible(ranked: RankedPaper, rules: RankingRules) -> bool:
    """§8.3: pertinent enough, meets minimums and filters, not read and not dismissed."""
    paper, prefs = ranked.paper, rules.preferences
    return (
        paper.pertinence_cos >= rules.gate
        and _meets_minimums(ranked.scores, prefs.minimums)
        and _passes_filters(paper, prefs)
        and not paper.state.read
        and not paper.state.dismissed
    )


def rank(papers: Iterable[GradedPaper], rules: RankingRules) -> list[RankedPaper]:
    """Eligible papers, best first: weighted score, then pertinence cosine, then newest."""
    scored = (score_paper(p, rules) for p in papers)
    eligible = [r for r in scored if is_eligible(r, rules)]
    return sorted(
        eligible,
        key=lambda r: (r.weighted, r.paper.pertinence_cos, r.paper.entrez_date),
        reverse=True,
    )
