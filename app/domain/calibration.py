"""Calibration maths (SPEC.md §12): stratified sampling and model-vs-surgeon agreement.

Pure: no I/O. Randomness comes in as a `random.Random`.
"""

import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.criteria import INTRINSIC_CRITERIA

SCALE = (1, 2, 3, 4, 5)
# SPEC §12 launch bar: within-±1 agreement on every criterion, stricter on proof strength.
LAUNCH_WITHIN_ONE = 0.80
LAUNCH_WITHIN_ONE_PROOF = 0.90

# Checked in order: a paper tagged both "Review" and "Systematic Review" is a systematic review.
_BUCKETS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "systematic review",
        frozenset({"Meta-Analysis", "Systematic Review", "Network Meta-Analysis"}),
    ),
    (
        "trial",
        frozenset(
            {
                "Randomized Controlled Trial",
                "Clinical Trial",
                "Clinical Trial, Phase II",
                "Clinical Trial, Phase III",
                "Controlled Clinical Trial",
                "Pragmatic Clinical Trial",
            }
        ),
    ),
    ("case report", frozenset({"Case Reports"})),
    ("narrative review", frozenset({"Review"})),
)


def design_bucket(pub_types: Sequence[str]) -> str:
    """Coarse study-design bucket from PubMed publication types."""
    types = set(pub_types)
    for name, tags in _BUCKETS:
        if types & tags:
            return name
    return "other"


def stratified_sample(
    candidates: Sequence[tuple[str, Sequence[str]]], n: int, rng: random.Random
) -> list[str]:
    """Pick up to n PMIDs, round-robin across design buckets so rare designs are represented.

    `candidates` is (pmid, pub_types). Within a bucket the order is random.
    """
    buckets: dict[str, list[str]] = defaultdict(list)
    for pmid, pub_types in candidates:
        buckets[design_bucket(pub_types)].append(pmid)
    queues = [buckets[name] for name in sorted(buckets)]
    for q in queues:
        rng.shuffle(q)
    picked: list[str] = []
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop())
    return picked


Pair = tuple[int, int]  # (surgeon, model)


def exact_agreement(pairs: Sequence[Pair]) -> float:
    return sum(s == m for s, m in pairs) / len(pairs)


def within_one_agreement(pairs: Sequence[Pair]) -> float:
    return sum(abs(s - m) <= 1 for s, m in pairs) / len(pairs)


def quadratic_weighted_kappa(pairs: Sequence[Pair]) -> float | None:
    """Cohen's kappa with quadratic weights on the 1-5 scale.

    None when undefined (both raters used a single identical value throughout).
    """
    k = len(SCALE)
    n = len(pairs)
    observed = [[0.0] * k for _ in range(k)]
    for s, m in pairs:
        observed[s - 1][m - 1] += 1
    hist_s = [sum(row) for row in observed]
    hist_m = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * observed[i][j]
            den += w * hist_s[i] * hist_m[j] / n
    if den == 0:
        return None
    return 1 - num / den


@dataclass(frozen=True)
class CriterionAgreement:
    criterion: str
    n: int
    exact: float
    within_one: float
    kappa: float | None

    @property
    def meets_launch_bar(self) -> bool:
        bar = LAUNCH_WITHIN_ONE_PROOF if self.criterion == "proof_strength" else LAUNCH_WITHIN_ONE
        return self.within_one >= bar


@dataclass(frozen=True)
class Disagreement:
    pmid: str
    total_gap: int
    gaps: dict[str, int]  # model minus surgeon, per criterion


@dataclass(frozen=True)
class CalibrationReport:
    n: int
    criteria: list[CriterionAgreement]
    disagreements: list[Disagreement]  # biggest first

    @property
    def meets_launch_bar(self) -> bool:
        return self.n > 0 and all(c.meets_launch_bar for c in self.criteria)


def _scores(raw: Mapping[str, object]) -> dict[str, int] | None:
    """The four criterion scores, or None if any is missing or off-scale."""
    out: dict[str, int] = {}
    for c in INTRINSIC_CRITERIA:
        v = raw.get(c)
        if not isinstance(v, int) or isinstance(v, bool) or v not in SCALE:
            return None
        out[c] = v
    return out


Scored = list[tuple[str, dict[str, int], dict[str, int]]]


def _scored_by_both(
    items: Sequence[tuple[str, Mapping[str, object], Mapping[str, object]]],
) -> Scored:
    both: Scored = []
    for pmid, raw_s, raw_m in items:
        s, m = _scores(raw_s), _scores(raw_m)
        if s is not None and m is not None:
            both.append((pmid, s, m))
    return both


def _disagreements(both: Scored) -> list[Disagreement]:
    """Per paper, model minus surgeon per criterion; biggest total gap first."""
    out = []
    for pmid, s, m in both:
        gaps = {c: m[c] - s[c] for c in INTRINSIC_CRITERIA}
        out.append(Disagreement(pmid, sum(abs(g) for g in gaps.values()), gaps))
    return sorted(out, key=lambda d: (-d.total_gap, d.pmid))


def build_report(
    items: Sequence[tuple[str, Mapping[str, object], Mapping[str, object]]],
) -> CalibrationReport:
    """Agreement per criterion over items scored by both. `items` is (pmid, surgeon, model)."""
    both = _scored_by_both(items)

    criteria = [
        CriterionAgreement(
            criterion=c,
            n=len(pairs),
            exact=exact_agreement(pairs),
            within_one=within_one_agreement(pairs),
            kappa=quadratic_weighted_kappa(pairs),
        )
        for c in INTRINSIC_CRITERIA
        if (pairs := [(s[c], m[c]) for _, s, m in both])
    ]
    return CalibrationReport(n=len(both), criteria=criteria, disagreements=_disagreements(both))
