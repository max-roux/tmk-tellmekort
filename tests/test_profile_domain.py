import math

import pytest

from app.domain.preferences import PreferencesError, parse_preferences
from app.domain.ranking import ProfileCoefficients, profile_vector
from app.domain.seeds import parse_seed_refs


def test_profile_vector_combines_terms_and_normalises() -> None:
    v = profile_vector(topics=[[1.0, 0.0], [1.0, 0.0]], seeds=[[0.0, 2.0]])
    assert v is not None
    assert v == pytest.approx([1 / math.sqrt(5), 2 / math.sqrt(5)])
    assert math.hypot(*v) == pytest.approx(1.0)


def test_profile_vector_liked_and_negative_terms() -> None:
    c = ProfileCoefficients(topics=1.0, seeds=1.0, liked=0.5, not_for_me=0.5)
    v = profile_vector(
        topics=[[1.0, 0.0]], liked=[[0.0, 2.0]], not_for_me=[[2.0, 0.0]], coefficients=c
    )
    assert v == pytest.approx([0.0, 1.0])  # (1,0) + (0,1) - (1,0)


def test_profile_vector_none_without_positive_terms_or_when_cancelled() -> None:
    assert profile_vector(topics=[], not_for_me=[[1.0, 0.0]]) is None
    c = ProfileCoefficients(not_for_me=1.0)
    assert profile_vector(topics=[[1.0, 0.0]], not_for_me=[[1.0, 0.0]], coefficients=c) is None


def test_parse_seed_refs() -> None:
    refs = parse_seed_refs(
        "12345678, PMID: 23456789\n"
        "https://pubmed.ncbi.nlm.nih.gov/34567890/\n"
        "10.1016/J.JOMS.2024.01.002; https://doi.org/10.1002/hed.27000.\n"
        "doi:10.1016/j.joms.2024.01.002 not-a-ref 12345678"
    )
    assert refs.pmids == ["12345678", "23456789", "34567890"]
    assert refs.dois == ["10.1016/j.joms.2024.01.002", "10.1002/hed.27000"]
    assert refs.unrecognised == ["not-a-ref"]
    assert parse_seed_refs("  ") == parse_seed_refs("")


def test_parse_preferences_defaults_and_values() -> None:
    p = parse_preferences({"w_novelty": "3", "min_proof_strength": "3", "hide_case_reports": "on"})
    assert p.weights["novelty"] == 3.0
    assert p.weights["pertinence"] == 1.0
    assert p.minimums == {
        "pertinence": None,
        "proof_strength": 3,
        "novelty": None,
        "depth": None,
        "practical_usefulness": None,
    }
    assert p.hide_case_reports
    assert not parse_preferences({}).hide_case_reports


@pytest.mark.parametrize(
    "form",
    [
        {"w_depth": "6"},
        {"w_depth": "-1"},
        {"w_depth": "lots"},
        {"min_depth": "0"},
        {"min_depth": "x"},
        {
            f"w_{c}": "0"
            for c in ("pertinence", "proof_strength", "novelty", "depth", "practical_usefulness")
        },
    ],
)
def test_parse_preferences_rejects(form: dict[str, str]) -> None:
    with pytest.raises(PreferencesError):
        parse_preferences(form)
