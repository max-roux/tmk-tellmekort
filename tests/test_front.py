from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import PipelineRun, Topic, User
from app.feed.front import beat, latest_run
from tests.feed_setup import user

pytestmark = pytest.mark.db
__all__ = ["user"]  # pytest fixture


def test_beat_lists_active_topic_labels_only(db_session: Session, user: User) -> None:
    db_session.add(
        Topic(user_id=user.id, label="Old", description="x", source="manual", active=False)
    )
    db_session.commit()
    assert beat(db_session, user.id) == ["Fibula"]


def test_latest_run_reads_the_newest_successful_run(db_session: Session) -> None:
    assert latest_run(db_session) is None
    stats = {"ingest": {"found": 240}, "narrow": {"candidates": 180}, "grade": {"graded": 97}}
    older = datetime(2026, 10, 18, 1, tzinfo=UTC)
    newer = datetime(2026, 10, 25, 1, tzinfo=UTC)
    db_session.add_all(
        [
            PipelineRun(started_at=older, status="ok", stats={"ingest": {"found": 1}}),
            PipelineRun(started_at=newer, status="ok", stats=stats),
            PipelineRun(started_at=datetime(2026, 11, 1, 1, tzinfo=UTC), status="failed"),
        ]
    )
    db_session.commit()
    figures = latest_run(db_session)
    assert figures is not None
    assert (figures.started_at, figures.found, figures.screened, figures.graded) == (
        newer,
        240,
        180,
        97,
    )


def test_latest_run_counts_missing_steps_as_zero(db_session: Session) -> None:
    db_session.add(
        PipelineRun(started_at=datetime(2026, 10, 25, tzinfo=UTC), status="ok", stats={"grade": {}})
    )
    db_session.commit()
    figures = latest_run(db_session)
    assert figures is not None and (figures.found, figures.screened, figures.graded) == (0, 0, 0)
