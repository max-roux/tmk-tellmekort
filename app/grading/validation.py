"""Validate and normalise model grades (SPEC.md §7.4). Pure: dict in, GradeData out."""

from dataclasses import dataclass
from typing import Any, Literal, TypeGuard

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


def _is_int(v: object) -> TypeGuard[int]:
    return isinstance(v, int) and not isinstance(v, bool)


def _required_text(raw: dict[str, Any], key: str, error: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GradeValidationError(error)
    return value.strip()


def _criterion(raw: dict[str, Any], c: str) -> tuple[int, str]:
    item = raw.get(c)
    if not isinstance(item, dict):
        raise GradeValidationError(f"{c}: missing")
    score = item.get("score")
    if not _is_int(score) or not 1 <= score <= 5:
        raise GradeValidationError(f"{c}: score {score!r} outside 1-5")
    return score, _required_text(item, "justification", f"{c}: empty justification")


def _sample_size(raw: dict[str, Any]) -> int | None:
    value = raw.get("sample_size")
    return value if _is_int(value) and value >= 0 else None


def validate_grade(raw: Any, input_source: InputSource) -> GradeData:
    """Reject out-of-range scores, empty justifications or a missing summary.

    Clamps depth to 4 when grading from the abstract only.
    """
    if not isinstance(raw, dict):
        raise GradeValidationError("grade is not an object")
    graded = {c: _criterion(raw, c) for c in INTRINSIC_CRITERIA}
    scores = {c: score for c, (score, _) in graded.items()}
    summary = _required_text(raw, "summary", "summary missing")
    why = _required_text(raw, "why_it_matters", "why_it_matters missing")
    if input_source == "abstract":
        scores["depth"] = min(scores["depth"], 4)
    return GradeData(
        study_design=str(raw.get("study_design") or "").strip() or "unspecified",
        sample_size=_sample_size(raw),
        scores=scores,
        justifications={c: text for c, (_, text) in graded.items()},
        summary=summary,
        why_it_matters=why,
    )
