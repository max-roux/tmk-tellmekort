from app.domain.suggestions import raised_weight, suggest_weight

EVEN = {
    "pertinence": 1.0,
    "proof_strength": 1.0,
    "novelty": 1.0,
    "depth": 1.0,
    "practical_usefulness": 1.0,
}


def scores(proof: int, novelty: int = 3) -> dict[str, int]:
    return {
        "pertinence": 3,
        "proof_strength": proof,
        "novelty": novelty,
        "depth": 3,
        "practical_usefulness": 3,
    }


LIKED = [scores(5, novelty=4)] * 10  # proof gap 2.0, novelty gap 1.0 vs OTHERS
OTHERS = [scores(3, novelty=3)] * 4


def test_suggests_the_criterion_with_the_biggest_gap() -> None:
    assert suggest_weight(LIKED, OTHERS, EVEN, dismissed=frozenset()) == "proof_strength"


def test_needs_ten_likes_and_something_to_compare_with() -> None:
    assert suggest_weight(LIKED[:9], OTHERS, EVEN, dismissed=frozenset()) is None
    assert suggest_weight(LIKED, [], EVEN, dismissed=frozenset()) is None


def test_no_suggestion_for_a_small_gap_or_the_top_weight() -> None:
    half = [scores(3), scores(4)] * 2  # mean 3.5: a gap of 0.5
    assert suggest_weight([scores(4)] * 10, half, EVEN, frozenset()) is None
    top_proof = {**EVEN, "proof_strength": 3.0}
    # Proof strength already has the sole highest weight: the next best gap is suggested.
    assert suggest_weight(LIKED, OTHERS, top_proof, dismissed=frozenset()) == "novelty"


def test_dismissed_suggestions_stay_dismissed() -> None:
    assert suggest_weight(LIKED, OTHERS, EVEN, dismissed=frozenset({"proof_strength"})) == "novelty"
    assert suggest_weight(LIKED, OTHERS, EVEN, frozenset({"proof_strength", "novelty"})) is None


def test_ties_at_the_top_can_still_be_raised_but_not_past_5() -> None:
    # Default even weights tie everything at the top; raising one still changes ranking.
    assert suggest_weight(LIKED, OTHERS, EVEN, frozenset()) == "proof_strength"
    maxed = {**EVEN, "proof_strength": 5.0, "novelty": 5.0}
    assert suggest_weight(LIKED, OTHERS, maxed, frozenset()) is None


def test_raised_weight_is_one_above_the_highest_capped_at_5() -> None:
    assert raised_weight(EVEN) == 2.0
    assert raised_weight({**EVEN, "depth": 4.5}) == 5.0
