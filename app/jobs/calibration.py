"""Calibration set: sample, grade, record surgeon scores, report (SPEC.md §12).

The set is one fixed list of PMIDs. Each rubric version gets its own rows; when the
version is bumped, rows are created for it with the surgeon's scores carried forward,
so only the model needs to re-grade.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import CalibrationItem, Grade, Paper
from app.domain.calibration import CalibrationReport, build_report, stratified_sample
from app.domain.criteria import INTRINSIC_CRITERIA
from app.grading.grader import Grader
from app.grading.rubric import RUBRIC_VERSION
from app.jobs.grade_papers import GradeStats, grade_sync


class CalibrationSetExistsError(Exception):
    pass


def create_sample(
    session: Session,
    n: int,
    today: date,
    rng: random.Random,
    *,
    window_days: int,
    replace: bool = False,
) -> list[str]:
    """Pick n recent papers stratified by study design and store them for this rubric."""
    if session.scalar(select(func.count()).select_from(CalibrationItem)):
        if not replace:
            raise CalibrationSetExistsError("a calibration set exists; pass replace=True")
        session.execute(delete(CalibrationItem))
    candidates = session.execute(
        select(Paper.pmid, Paper.pub_types)
        .where(Paper.entrez_date >= today - timedelta(days=window_days))
        .order_by(Paper.pmid)
    ).all()
    pmids = stratified_sample([(p, t) for p, t in candidates], n, rng)
    session.add_all(CalibrationItem(pmid=p, rubric_version=RUBRIC_VERSION) for p in pmids)
    session.commit()
    return pmids


def current_items(session: Session) -> list[CalibrationItem]:
    """Items for the current rubric version, creating them from the latest older set if needed."""
    items = list(
        session.scalars(
            select(CalibrationItem)
            .where(CalibrationItem.rubric_version == RUBRIC_VERSION)
            .order_by(CalibrationItem.created_at, CalibrationItem.pmid)
        )
    )
    if items:
        return items
    latest = session.scalar(
        select(func.max(CalibrationItem.rubric_version)).where(
            CalibrationItem.rubric_version < RUBRIC_VERSION
        )
    )
    if latest is None:
        return []
    previous = session.scalars(
        select(CalibrationItem)
        .where(CalibrationItem.rubric_version == latest)
        .order_by(CalibrationItem.created_at, CalibrationItem.pmid)
    ).all()
    items = [
        CalibrationItem(pmid=p.pmid, rubric_version=RUBRIC_VERSION, surgeon_scores=p.surgeon_scores)
        for p in previous
    ]
    session.add_all(items)
    session.commit()
    return items


def _latest_grades(
    session: Session, pmids: list[str], version: int = RUBRIC_VERSION
) -> dict[str, Grade]:
    """The latest grade per PMID for a rubric version (the current grade, by default)."""
    grades: dict[str, Grade] = {}
    for g in session.scalars(
        select(Grade)
        .where(Grade.pmid.in_(pmids), Grade.rubric_version == version)
        .order_by(Grade.created_at)
    ):
        grades[g.pmid] = g
    return grades


@dataclass
class CalibrationGradeStats:
    grading: GradeStats
    items: int
    with_model_scores: int


def grade_set(session: Session, grader: Grader, today: date) -> CalibrationGradeStats:
    """Grade the set under the current rubric and snapshot the model's scores."""
    items = current_items(session)
    pmids = [i.pmid for i in items]
    stats = grade_sync(session, grader, pmids, today)
    grades = _latest_grades(session, pmids)
    for item in items:
        if g := grades.get(item.pmid):
            item.model_scores = {c: getattr(g, c) for c in INTRINSIC_CRITERIA}
    session.commit()
    return CalibrationGradeStats(
        grading=stats,
        items=len(items),
        with_model_scores=sum(i.model_scores is not None for i in items),
    )


def save_surgeon_scores(
    session: Session, item_id: uuid.UUID, scores: dict[str, int], comment: str
) -> None:
    item = session.get(CalibrationItem, item_id)
    if item is None or item.rubric_version != RUBRIC_VERSION:
        raise LookupError(f"no current calibration item {item_id}")
    if set(scores) != set(INTRINSIC_CRITERIA) or not all(1 <= v <= 5 for v in scores.values()):
        raise ValueError("need a 1-5 score for every criterion")
    item.surgeon_scores = {**scores, "comment": comment.strip()}
    session.commit()


@dataclass(frozen=True)
class ReportRow:
    pmid: str
    title: str
    surgeon: dict[str, object]
    model: dict[str, int]
    justifications: dict[str, str]


def calibration_report(
    session: Session, version: int = RUBRIC_VERSION
) -> tuple[CalibrationReport, dict[str, ReportRow]]:
    rows = session.execute(
        select(CalibrationItem, Paper.title)
        .join(Paper, Paper.pmid == CalibrationItem.pmid)
        .where(CalibrationItem.rubric_version == version)
    ).all()
    grades = _latest_grades(session, [i.pmid for i, _ in rows], version)
    detail = {
        item.pmid: ReportRow(
            pmid=item.pmid,
            title=title,
            surgeon=item.surgeon_scores or {},
            model=item.model_scores or {},
            justifications=grades[item.pmid].justifications if item.pmid in grades else {},
        )
        for item, title in rows
    }
    report = build_report([(r.pmid, r.surgeon, r.model) for r in detail.values()])
    return report, detail
