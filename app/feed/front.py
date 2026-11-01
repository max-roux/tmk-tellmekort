"""Read-only extras for the front page's sidebar boxes (SPEC.md §11.2)."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PipelineRun, Topic


def beat(session: Session, user_id: uuid.UUID) -> list[str]:
    """The labels of the user's active topics, in the order they were added."""
    return list(
        session.scalars(
            select(Topic.label)
            .where(Topic.user_id == user_id, Topic.active)
            .order_by(Topic.created_at, Topic.label)
        )
    )


@dataclass(frozen=True)
class RunFigures:
    started_at: datetime
    found: int  # records the specialty query returned from PubMed
    screened: int  # papers scored against every profile when narrowing
    graded: int


def _count(stats: dict[str, Any], step: str, key: str) -> int:
    value = stats.get(step, {}).get(key, 0)
    return value if isinstance(value, int) else 0


def latest_run(session: Session) -> RunFigures | None:
    """Figures from the latest successful weekly run, or None before the first one."""
    run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.status == "ok")
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    return RunFigures(
        started_at=run.started_at,
        found=_count(run.stats, "ingest", "found"),
        screened=_count(run.stats, "narrow", "candidates"),
        graded=_count(run.stats, "grade", "graded"),
    )
