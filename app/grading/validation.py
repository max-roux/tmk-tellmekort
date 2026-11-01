"""Validate and normalise model grades (SPEC.md §7.4). Pure: dict in, GradeData out."""

from dataclasses import dataclass
from typing import Any, Literal

from app.domain.criteria import INTRINSIC_CRITERIA

InputSource = Literal["full_text", "abstract"]


class GradeValidationError(ValueError):
    pass


@dataclass(frozen=True)
class GradeData:
    study_design: str
    sample_size: int | None
    scores: dict[str, int]
    justifications: dict[str, str]
    summary: str
    why_it_matters: str


def validate_grade(raw: Any, input_source: InputSource) -> GradeData:
    """Reject out-of-range scores, empty justifications or a missing summary.

    Clamps depth to 4 when grading from the abstract only.
    """
    if not isinstance(raw, dict):
        raise GradeValidationError("grade is not an object")

    scores: dict[str, int] = {}
    justifications: dict[str, str] = {}
    for c in INTRINSIC_CRITERIA:
        item = raw.get(c)
        if not isinstance(item, dict):
            raise GradeValidationError(f"{c}: missing")
        score = item.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            raise GradeValidationError(f"{c}: score {score!r} outside 1-5")
        justification = item.get("justification")
        if not isinstance(justification, str) or not justification.strip():
            raise GradeValidationError(f"{c}: empty justification")
        scores[c] = score
        justifications[c] = justification.strip()

    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise GradeValidationError("summary missing")
    why = raw.get("why_it_matters")
    if not isinstance(why, str) or not why.strip():
        raise GradeValidationError("why_it_matters missing")

    if input_source == "abstract" and scores["depth"] == 5:
        scores["depth"] = 4

    sample_size = raw.get("sample_size")
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 0:
        sample_size = None

    return GradeData(
        study_design=str(raw.get("study_design") or "").strip() or "unspecified",
        sample_size=sample_size,
        scores=scores,
        justifications=justifications,
        summary=summary.strip(),
        why_it_matters=why.strip(),
    )
