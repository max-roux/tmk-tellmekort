import copy
import json

import pytest

from app.grading.validation import GradeValidationError, validate_grade
from tests.fakes import message

VALID = json.loads(message()["content"][1]["text"])


def raw(**changes: object) -> dict:
    d = copy.deepcopy(VALID)
    d.update(changes)
    return d


def test_valid_grade_full_text_keeps_depth_5() -> None:
    g = validate_grade(VALID, "full_text")
    assert g.scores == {"proof_strength": 4, "novelty": 3, "depth": 5, "practical_usefulness": 4}
    assert g.study_design == "RCT"
    assert g.sample_size == 40
    assert set(g.justifications) == set(g.scores)


def test_abstract_only_clamps_depth_to_4() -> None:
    assert validate_grade(VALID, "abstract").scores["depth"] == 4


@pytest.mark.parametrize("score", [0, 6, "4", 4.0, True, None])
def test_rejects_bad_scores(score: object) -> None:
    with pytest.raises(GradeValidationError, match="novelty"):
        validate_grade(raw(novelty={"score": score, "justification": "x"}), "abstract")


@pytest.mark.parametrize("justification", ["", "   ", None])
def test_rejects_empty_justification(justification: object) -> None:
    with pytest.raises(GradeValidationError, match="justification"):
        validate_grade(raw(depth={"score": 3, "justification": justification}), "abstract")


def test_rejects_missing_summary_and_criterion() -> None:
    with pytest.raises(GradeValidationError, match="summary"):
        validate_grade(raw(summary=" "), "abstract")
    d = raw()
    del d["proof_strength"]
    with pytest.raises(GradeValidationError, match="proof_strength"):
        validate_grade(d, "abstract")
    with pytest.raises(GradeValidationError):
        validate_grade([], "abstract")


def test_bad_sample_size_becomes_none_and_empty_design_is_unspecified() -> None:
    g = validate_grade(raw(sample_size=-3, study_design=""), "abstract")
    assert g.sample_size is None
    assert g.study_design == "unspecified"
