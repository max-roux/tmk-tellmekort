"""Regrade the active window after a rubric change (SPEC.md §13).

Papers in the window graded only under older rubric versions get a current-version grade,
newest first, under the same spend guard as the weekly run. Old grade rows are kept.
Idempotent: a paper is only stale until it has a current grade.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Grade, Paper
from app.email.base import Mailer
from app.grading.grader import Grader
from app.jobs.grade_papers import Polling, currently_graded
from app.jobs.weekly_pipeline import BATCH_WAIT, grade_with_guard
from app.sources.pubmed import PubMedClient


def stale_pmids(session: Session, since: date) -> list[str]:
    """Graded papers entered since `since` with no current-version grade, newest first."""
    stmt = (
        select(Paper.pmid)
        .join(Grade, Grade.pmid == Paper.pmid)
        .where(Paper.entrez_date >= since, Paper.pmid.not_in(currently_graded()))
        .group_by(Paper.pmid, Paper.entrez_date)
        .order_by(Paper.entrez_date.desc(), Paper.pmid.desc())
    )
    return list(session.scalars(stmt))


def regrade(
    session: Session,
    pubmed: PubMedClient,
    grader: Grader,
    mailer: Mailer,
    settings: Settings,
    today: date,
    *,
    window_days: int,
    poll: Polling | None = None,
) -> dict[str, Any]:
    todo = stale_pmids(session, today - timedelta(days=window_days))
    poll = poll or Polling(timeout=BATCH_WAIT.total_seconds())
    return grade_with_guard(session, pubmed, grader, mailer, settings, today, todo, poll)
