import pytest

from app.domain.narrowing import narrow_scores, select_for_grading


def test_scores_are_max_cosine_over_references() -> None:
    papers = {"a": [1.0, 0.0], "b": [0.0, 2.0], "c": [1.0, 1.0], "zero": [0.0, 0.0]}
    scores = narrow_scores(papers, [[3.0, 0.0], [0.0, 1.0]])  # anchor + one profile
    assert scores["a"] == pytest.approx(1.0)
    assert scores["b"] == pytest.approx(1.0)  # matches the profile, not the anchor
    assert scores["c"] == pytest.approx(0.7071, abs=1e-4)
    assert scores["zero"] == 0.0


def test_no_references_scores_zero() -> None:
    assert narrow_scores({"a": [1.0]}, []) == {"a": 0.0}
    assert narrow_scores({}, [[1.0]]) == {}


def test_select_top_n_with_deterministic_ties_and_seeds() -> None:
    scores = {"10": 0.9, "11": 0.5, "12": 0.5, "13": 0.1}
    assert select_for_grading(scores, 2) == {"10", "12"}  # tie on 0.5: higher PMID wins
    assert select_for_grading(scores, 2, always_include={"13", "not-a-candidate"}) == {
        "10",
        "12",
        "13",
    }
    assert select_for_grading(scores, 10) == set(scores)
