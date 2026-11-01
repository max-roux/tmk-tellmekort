import random

import pytest

from app.domain.calibration import (
    build_report,
    design_bucket,
    exact_agreement,
    quadratic_weighted_kappa,
    stratified_sample,
    within_one_agreement,
)
from app.domain.criteria import INTRINSIC_CRITERIA


@pytest.mark.parametrize(
    ("pub_types", "bucket"),
    [
        (["Journal Article", "Review", "Systematic Review"], "systematic review"),
        (["Meta-Analysis"], "systematic review"),
        (["Randomized Controlled Trial", "Journal Article"], "trial"),
        (["Case Reports"], "case report"),
        (["Review"], "narrative review"),
        (["Journal Article", "Observational Study"], "other"),
        ([], "other"),
    ],
)
def test_design_bucket(pub_types: list[str], bucket: str) -> None:
    assert design_bucket(pub_types) == bucket


def test_stratified_sample_round_robins_across_buckets() -> None:
    candidates = [(f"o{i}", ["Journal Article"]) for i in range(30)]
    candidates += [(f"r{i}", ["Randomized Controlled Trial"]) for i in range(3)]
    candidates += [("c0", ["Case Reports"])]
    picked = stratified_sample(candidates, 8, random.Random(1))
    assert len(picked) == 8 and len(set(picked)) == 8
    assert "c0" in picked
    assert sum(p.startswith("r") for p in picked) == 3  # all rare RCTs included
    assert picked == stratified_sample(candidates, 8, random.Random(1))  # seeded


def test_stratified_sample_returns_all_when_too_few() -> None:
    assert sorted(stratified_sample([("a", []), ("b", ["Review"])], 20, random.Random())) == [
        "a",
        "b",
    ]


def test_agreement_rates() -> None:
    pairs = [(3, 3), (3, 4), (2, 5), (1, 1)]
    assert exact_agreement(pairs) == 0.5
    assert within_one_agreement(pairs) == 0.75


def test_quadratic_weighted_kappa() -> None:
    assert quadratic_weighted_kappa([(1, 1), (3, 3), (5, 5)]) == pytest.approx(1.0)
    # Raters independent of each other: kappa 0.
    assert quadratic_weighted_kappa([(1, 1), (1, 2), (2, 1), (2, 2)]) == pytest.approx(0.0)
    # Systematically reversed: strongly negative.
    assert quadratic_weighted_kappa([(1, 5), (5, 1), (3, 3)]) < -0.5  # type: ignore[operator]
    # A near-miss costs less than a far miss.
    near = quadratic_weighted_kappa([(1, 1), (5, 5), (3, 4)])
    far = quadratic_weighted_kappa([(1, 1), (5, 5), (3, 1)])
    assert near is not None and far is not None and near > far
    # Everyone always says 3: undefined.
    assert quadratic_weighted_kappa([(3, 3), (3, 3)]) is None


def scores(*vals: int) -> dict[str, int]:
    return dict(zip(INTRINSIC_CRITERIA, vals, strict=True))


def test_build_report_launch_bar_and_disagreements() -> None:
    items = [
        ("p1", scores(4, 3, 3, 4), scores(4, 3, 3, 4)),
        ("p2", scores(2, 2, 2, 2), scores(3, 2, 2, 3)),
        ("p3", scores(1, 2, 2, 2), scores(4, 2, 3, 2)),
        ("p4", {**scores(3, 3, 3, 3), "comment": "x"}, scores(3, 3, 3, 3)),
        ("unscored", {}, scores(3, 3, 3, 3)),
        ("ungraded", scores(3, 3, 3, 3), {}),
    ]
    r = build_report(items)
    assert r.n == 4
    proof = next(c for c in r.criteria if c.criterion == "proof_strength")
    assert proof.exact == 0.5 and proof.within_one == 0.75
    assert not proof.meets_launch_bar  # needs 90% on proof strength
    novelty = next(c for c in r.criteria if c.criterion == "novelty")
    assert novelty.within_one == 1.0 and novelty.meets_launch_bar
    assert not r.meets_launch_bar
    assert [d.pmid for d in r.disagreements[:2]] == ["p3", "p2"]
    assert r.disagreements[0].gaps == {
        "proof_strength": 3,
        "novelty": 0,
        "depth": 1,
        "practical_usefulness": 0,
    }


def test_empty_report_never_meets_bar() -> None:
    r = build_report([])
    assert r.n == 0 and r.criteria == [] and not r.meets_launch_bar
