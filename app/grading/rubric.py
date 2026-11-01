"""Grading rubric and output schema (SPEC.md §7.2-7.3).

Any change to RUBRIC_TEXT or GRADE_SCHEMA must bump RUBRIC_VERSION: grades are
keyed by version, and ranking only uses grades for the current one.
"""

from dataclasses import dataclass
from typing import Any

RUBRIC_VERSION = 1

RUBRIC_TEXT = """\
You grade research papers for a practising maxillofacial surgeon. For each paper you \
receive metadata, the abstract, and sometimes the full text. Score four criteria from \
1 to 5 using the scales below, and give each score a justification of at most 25 words \
that names the specific feature of the paper that drove it.

Grade what the paper reports, not its topic. A paper outside oral and maxillofacial \
surgery is graded on the same scales; relevance to the surgeon is assessed elsewhere.

## Proof strength
How strong the evidence is that the main claim is true.
- 5: Systematic review/meta-analysis of RCTs, or a large well-conducted multicentre RCT.
- 4: Single RCT with adequate size and low risk of bias, or systematic review of mostly \
non-randomised studies.
- 3: Prospective cohort or well-controlled comparative study; small or open-label RCT \
with notable limitations.
- 2: Retrospective cohort, case-control or case series with comparison; cadaver or \
in-vitro biomechanics study.
- 1: Case report, small uncontrolled case series, narrative review, expert opinion, \
technical note.
- Adjust by at most 1 point for size, follow-up length and risk of bias; justify the \
adjustment.

## Novelty
What the paper adds to existing knowledge (not how recent it is).
- 5: First evidence for a new technique, finding or concept, or overturns current practice.
- 4: Substantial new evidence on an open question (e.g. first RCT where only cohorts existed).
- 3: Meaningful extension: new population, longer follow-up, head-to-head comparison.
- 2: Mostly confirms known results with minor variation.
- 1: Replicates well-established knowledge; nothing new for a specialist.

## Depth
How thorough and rigorous the work is.
- 5: Rigorous methods fully reported, appropriate statistics, long follow-up, \
limitations and confounders addressed.
- 4: Solid methods and reporting with minor gaps.
- 3: Adequate but with clear gaps (short follow-up, limited outcomes, thin statistics).
- 2: Superficial: few outcomes, weak analysis, unclear methods.
- 1: Anecdotal or descriptive only.
- If grading from the abstract only, cap at 4 and say so.

## Practical usefulness
Whether a practising maxillofacial surgeon could act on it.
- 5: Directly changes or confirms a common clinical decision; ready to apply.
- 4: Clear clinical implication for a common scenario, with some caveats.
- 3: Relevant to practice, but niche or needing more evidence first.
- 2: Mainly of research or academic interest.
- 1: No foreseeable clinical application.

## Other fields
- study_design: the design as reported, e.g. "RCT", "retrospective cohort", \
"systematic review with meta-analysis", "case report".
- sample_size: number of patients (or specimens) analysed, or null if not stated or \
not applicable.
- summary: 2-3 sentences in plain clinical English: what was studied, how, and the \
main result with numbers where given.
- why_it_matters: 1 sentence on what a practising maxillofacial surgeon could do \
differently because of this paper.
"""


@dataclass(frozen=True)
class CriterionGuide:
    key: str
    name: str
    description: str
    levels: dict[int, str]  # 5..1
    notes: list[str]


def criterion_guides() -> list[CriterionGuide]:
    """The rubric scales, parsed from RUBRIC_TEXT, for showing to the surgeon."""
    guides: list[CriterionGuide] = []
    for section in RUBRIC_TEXT.split("\n## ")[1:]:
        heading, _, body = section.partition("\n")
        if heading.strip() == "Other fields":
            continue
        lines = [ln.strip() for ln in body.strip().splitlines()]
        levels: dict[int, str] = {}
        notes: list[str] = []
        for ln in lines[1:]:
            item = ln.removeprefix("- ")
            score, sep, text = item.partition(": ")
            if sep and score.isdigit():
                levels[int(score)] = text
            else:
                notes.append(item)
        guides.append(
            CriterionGuide(
                key=heading.strip().lower().replace(" ", "_"),
                name=heading.strip(),
                description=lines[0],
                levels=levels,
                notes=notes,
            )
        )
    return guides


def _criterion() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
            "justification": {"type": "string"},
        },
        "required": ["score", "justification"],
        "additionalProperties": False,
    }


GRADE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "study_design": {"type": "string"},
        "sample_size": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "proof_strength": _criterion(),
        "novelty": _criterion(),
        "depth": _criterion(),
        "practical_usefulness": _criterion(),
        "summary": {"type": "string"},
        "why_it_matters": {"type": "string"},
    },
    "required": [
        "study_design",
        "sample_size",
        "proof_strength",
        "novelty",
        "depth",
        "practical_usefulness",
        "summary",
        "why_it_matters",
    ],
    "additionalProperties": False,
}
