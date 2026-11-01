from datetime import date

import pytest

from app.domain.preferences import Preferences
from app.domain.ranking import (
    GradedPaper,
    PaperState,
    RankingRules,
    derive_state,
    pertinence_cosines,
    pertinence_score,
    rank,
    weighted_score,
)

THRESHOLDS = (0.30, 0.40, 0.50, 0.60)
EVEN = {
    "pertinence": 1.0,
    "proof_strength": 1.0,
    "novelty": 1.0,
    "depth": 1.0,
    "practical_usefulness": 1.0,
}
NO_MINIMUMS = dict.fromkeys(EVEN)


def prefs(**overrides: object) -> Preferences:
    base: dict[str, object] = {
        "weights": EVEN,
        "minimums": NO_MINIMUMS,
        "hide_case_reports": False,
        "study_types": None,
    }
    return Preferences(**{**base, **overrides})  # type: ignore[arg-type]


def rules(**overrides: object) -> RankingRules:
    return RankingRules(preferences=prefs(**overrides), gate=0.30, thresholds=THRESHOLDS)


def paper(pmid: str, score: int = 3, cos: float = 0.55, **kw: object) -> GradedPaper:
    fields: dict[str, object] = {
        "pmid": pmid,
        "scores": {
            "proof_strength": score,
            "novelty": score,
            "depth": score,
            "practical_usefulness": score,
        },
        "pertinence_cos": cos,
        "entrez_date": date(2026, 10, 1),
        "pub_types": ("Journal Article",),
        "state": PaperState(),
    }
    return GradedPaper(**{**fields, **kw})  # type: ignore[arg-type]


def test_state_last_event_of_each_pair_wins() -> None:
    assert derive_state([]) == PaperState(read=False, liked=False, dismissed=False)
    assert derive_state(["like", "read", "unlike"]) == PaperState(read=True, liked=False)
    assert derive_state(["not_for_me", "like", "undismiss", "unread", "read"]) == PaperState(
        read=True, liked=True, dismissed=False
    )
    assert derive_state(["undismiss", "not_for_me"]).dismissed


@pytest.mark.parametrize(
    ("cos", "expected"),
    [(-0.2, 1), (0.299, 1), (0.30, 2), (0.45, 3), (0.50, 4), (0.599, 4), (0.60, 5), (0.99, 5)],
)
def test_pertinence_score_thresholds(cos: float, expected: int) -> None:
    assert pertinence_score(cos, THRESHOLDS) == expected


def test_pertinence_cos_is_best_of_profile_and_any_topic() -> None:
    papers = {"a": [1.0, 0.0], "b": [0.0, 3.0], "c": [-1.0, 0.0]}
    cos = pertinence_cosines(papers, profile=[1.0, 1.0], topics=[[0.0, 1.0]])
    assert cos["a"] == pytest.approx(0.7071, abs=1e-4)  # profile only
    assert cos["b"] == pytest.approx(1.0)  # a niche topic beats the diluted profile
    assert cos["c"] == pytest.approx(0.0)  # topic cosine 0 beats profile cosine -0.71
    assert pertinence_cosines({}, profile=[1.0], topics=[]) == {}


def test_weighted_score_is_weighted_mean() -> None:
    s = {"pertinence": 5, "proof_strength": 1, "novelty": 3, "depth": 3, "practical_usefulness": 3}
    assert weighted_score(s, EVEN) == pytest.approx(3.0)
    w = {**EVEN, "pertinence": 3.0, "novelty": 0.0}
    assert weighted_score(s, w) == pytest.approx((15 + 1 + 3 + 3) / 6)


def test_rank_orders_by_weighted_then_pertinence_then_newest() -> None:
    ranked = rank(
        [
            paper("low", score=2),
            paper("top", score=5),
            paper("tie-older", score=3, cos=0.55, entrez_date=date(2026, 9, 1)),
            paper("tie-newer", score=3, cos=0.55, entrez_date=date(2026, 10, 9)),
            paper("tie-closer", score=3, cos=0.58),
        ],
        rules(),
    )
    assert [r.paper.pmid for r in ranked] == ["top", "tie-closer", "tie-newer", "tie-older", "low"]
    assert ranked[0].pertinence == 4 and ranked[0].weighted == pytest.approx((4 + 5 * 4) / 5)


def test_rank_drops_ineligible_papers() -> None:
    ranked = rank(
        [
            paper("ok"),
            paper("off-topic", cos=0.29),
            paper("read", state=PaperState(read=True)),
            paper("dismissed", state=PaperState(dismissed=True)),
            paper("liked-only", state=PaperState(liked=True)),
            paper("weak", score=2),
            paper("case", pub_types=("Case Reports",)),
            paper("trial", pub_types=("Randomized Controlled Trial",)),
        ],
        rules(
            minimums={**NO_MINIMUMS, "proof_strength": 3},
            hide_case_reports=True,
        ),
    )
    assert {r.paper.pmid for r in ranked} == {"ok", "liked-only", "trial"}


def test_rank_filters_study_types_and_pertinence_minimum() -> None:
    papers = [
        paper("trial", pub_types=("Randomized Controlled Trial",)),
        paper("review", pub_types=("Review",)),
        paper("loose", cos=0.35, pub_types=("Randomized Controlled Trial",)),
    ]
    only_trials = rank(papers, rules(study_types=frozenset({"trial"})))
    assert {r.paper.pmid for r in only_trials} == {"trial", "loose"}
    strict = rank(papers, rules(minimums={**NO_MINIMUMS, "pertinence": 3}))
    assert {r.paper.pmid for r in strict} == {"trial", "review"}
