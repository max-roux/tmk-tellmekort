"""cli.py weekly: the summary is printed from the run the pipeline committed."""

from contextlib import nullcontext
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from typer.testing import CliRunner

import cli
from app.config import Settings
from app.db.models import PipelineRun
from tests.fakes import FakeEmbedder

STATS = {
    "ingest": {"stored": 12},
    "grade": {"graded": 99, "dropped": 0, "month_usd": 0.83},
}


class ClosableEmbedder(FakeEmbedder):
    def close(self) -> None:
        pass


def fake_run_weekly(session: Session, settings: Any, clients: Any, now: datetime) -> PipelineRun:
    # Like run_weekly: the run row is committed, which expires its attributes.
    run = PipelineRun(started_at=now, stats=STATS)
    session.add(run)
    session.commit()
    return run


def test_weekly_prints_the_summary_after_the_run(
    migrated_url: str, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(migrated_url)
    monkeypatch.setattr(cli, "get_engine", lambda: engine)
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))  # type: ignore[call-arg]
    monkeypatch.setattr(cli, "_embedder", ClosableEmbedder)
    monkeypatch.setattr(cli, "_pubmed", nullcontext)
    monkeypatch.setattr(cli, "_grader", lambda: None)
    monkeypatch.setattr(cli, "run_weekly", fake_run_weekly)

    result = CliRunner().invoke(cli.cli, ["weekly"])
    engine.dispose()
    assert result.exit_code == 0, result.output
    assert "stored 12 papers, graded 99 (dropped by the cap 0), $0.83" in result.output
