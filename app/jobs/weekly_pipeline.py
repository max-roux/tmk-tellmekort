"""The weekly pipeline (SPEC.md §6): fetch, embed, narrow, full text, grade, with the
spend guard (§6.6) and admin alerts. Run by `cli.py weekly` from a Sunday cron job.

Every step is idempotent, so a failed run can simply be run again; an unfinished grading
batch is collected by the next run.
"""

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Paper, PipelineRun
from app.domain.spend import Budget, crossed_alert_line, fit_budget
from app.email.alerts import alert_admin
from app.email.base import Mailer
from app.embeddings.base import Embedder
from app.grading.cost import month_spend
from app.grading.grader import GradeInput, Grader, estimate_cost
from app.jobs.embed_papers import embed_papers
from app.jobs.full_text import fetch_full_texts
from app.jobs.grade_papers import Polling, grade_batch
from app.jobs.narrow_candidates import (
    load_anchor,
    narrow,
    selected_ungraded,
    user_references,
    week_of,
)
from app.jobs.weekly_ingest import ingest
from app.profiles.service import coefficients, embed_topics, refresh_all_profiles
from app.sources.pubmed import PubMedClient, load_specialty_query

log = logging.getLogger(__name__)

INGEST_DAYS = 14  # overlaps the previous run; stored papers are skipped
# Render stops a cron run after 12 hours; leave room for the steps before grading.
BATCH_WAIT = timedelta(hours=10)


@dataclass(frozen=True)
class Clients:
    pubmed: PubMedClient
    embedder: Embedder
    grader: Grader
    mailer: Mailer


def _ingest(session: Session, c: Clients, today: date) -> dict[str, Any]:
    start = today - timedelta(days=INGEST_DAYS - 1)
    return asdict(ingest(session, c.pubmed, load_specialty_query(), start, today))


def _embed(session: Session, c: Clients, settings: Settings) -> dict[str, Any]:
    papers = embed_papers(session, c.embedder)
    topics = embed_topics(session, c.embedder)
    profiles = refresh_all_profiles(session, c.embedder.model, coefficients(settings))
    return {
        "papers": papers.embedded,
        "tokens": papers.tokens,
        "topics": topics,
        "profiles": profiles,
    }


def _narrow(session: Session, c: Clients, settings: Settings, today: date) -> dict[str, Any]:
    refs = user_references(session, c.embedder.model)
    stats = narrow(
        session,
        c.embedder,
        since=today - timedelta(days=settings.active_window_days),
        week=week_of(today),
        limit=settings.grade_limit_per_week,
        anchor_text=load_anchor(),
        profile_vectors=refs.vectors,
        always_include=refs.seeds,
    )
    return asdict(stats)


def _budget(
    session: Session,
    grader: Grader,
    settings: Settings,
    today: date,
    todo: list[str],
    texts: dict[str, str],
) -> Budget:
    """Which of `todo` (in priority order) to grade under the monthly cap."""
    papers = {p.pmid: p for p in session.scalars(select(Paper).where(Paper.pmid.in_(todo)))}
    estimates = [
        (pmid, estimate_cost(grader.model, GradeInput(papers[pmid], texts.get(pmid))))
        for pmid in todo
    ]
    cap = Decimal(str(settings.llm_monthly_cap_usd))
    return fit_budget(estimates, spent=month_spend(session, today), cap=cap)


def grade_with_guard(
    session: Session,
    pubmed: PubMedClient,
    grader: Grader,
    mailer: Mailer,
    settings: Settings,
    today: date,
    todo: list[str],
    poll: Polling,
) -> dict[str, Any]:
    """Grade `todo` (priority order) by batch under the spend guard (SPEC.md §6.6).

    Fetches open-access full text, keeps what fits under the cap, alerts the admin when
    the cap cuts grading short or spend crosses 80% of it.
    """
    texts = fetch_full_texts(session, pubmed, todo, settings.fulltext_max_tokens)
    budget = _budget(session, grader, settings, today, todo, texts)
    if budget.truncated:
        alert_admin(
            mailer,
            settings,
            "Spend cap reached: grading cut short",
            f"Grading {len(budget.kept)} of {len(todo)} papers to stay under "
            f"LLM_MONTHLY_CAP_USD={settings.llm_monthly_cap_usd}. The other "
            f"{len(budget.dropped)} wait for next month or a higher cap.",
        )
    before = month_spend(session, today)
    stats = grade_batch(session, grader, budget.kept, today, poll=poll, full_texts=texts)
    after = month_spend(session, today)
    cap = Decimal(str(settings.llm_monthly_cap_usd))
    if crossed_alert_line(before, after, cap):
        alert_admin(
            mailer,
            settings,
            "LLM spend passed 80% of the monthly cap",
            f"${after:.2f} of ${cap:.2f} spent this month.",
        )
    return {
        "todo": len(todo),
        "full_text": len(texts),
        "kept": len(budget.kept),
        "dropped": len(budget.dropped),
        "estimate_usd": float(budget.estimate),
        "graded": stats.graded,
        "retried": stats.retried,
        "failed": stats.failed,
        "usd": float(stats.usd),
        "month_usd": float(after),
    }


def run_weekly(
    session: Session,
    settings: Settings,
    c: Clients,
    now: datetime,
    poll: Polling | None = None,
) -> PipelineRun:
    """Run every step, recording stats as it goes. On failure, record, alert and re-raise."""
    poll = poll or Polling(timeout=BATCH_WAIT.total_seconds())
    today = now.date()
    run = PipelineRun(started_at=now, stats={})
    session.add(run)
    session.commit()
    steps: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("ingest", lambda: _ingest(session, c, today)),
        ("embed", lambda: _embed(session, c, settings)),
        ("narrow", lambda: _narrow(session, c, settings, today)),
        (
            "grade",
            lambda: grade_with_guard(
                session,
                c.pubmed,
                c.grader,
                c.mailer,
                settings,
                today,
                selected_ungraded(session),
                poll,
            ),
        ),
    ]
    try:
        for name, step in steps:
            result = step()
            run.stats = {**run.stats, name: result}
            session.commit()
            log.info("%s: %s", name, result)
    except Exception as e:
        session.rollback()
        run.status, run.error = "failed", f"{type(e).__name__}: {e}"
        run.finished_at = datetime.now(UTC)
        session.commit()
        alert_admin(
            c.mailer,
            settings,
            "Weekly pipeline failed",
            f"Step stats so far: {run.stats}\nError: {run.error}\n"
            "Every step is safe to re-run: cli.py weekly.",
        )
        raise
    run.status, run.finished_at = "ok", datetime.now(UTC)
    session.commit()
    return run
