"""Weekly ingest, step 5: grade papers and store results (SPEC.md §6.5).

Idempotent: papers that already have a grade for the current RUBRIC_VERSION are skipped,
and an open batch from an earlier run is collected instead of paying for a new one.
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Grade, GradingBatch, Paper
from app.grading.cost import record_spend
from app.grading.grader import GradeFailure, GradeInput, GradeOutcome, Grader, GradeResult
from app.grading.rubric import RUBRIC_VERSION

log = logging.getLogger(__name__)

BATCH_TIMEOUT_S = 24 * 3600
POLL_INTERVAL_S = 60


class BatchTimeoutError(Exception):
    pass


@dataclass(frozen=True)
class Polling:
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    interval: float = POLL_INTERVAL_S
    timeout: float = BATCH_TIMEOUT_S


@dataclass
class GradeStats:
    submitted: int = 0
    graded: int = 0
    retried: int = 0
    failed: list[str] = field(default_factory=list)
    usd: Decimal = Decimal(0)


def has_current_grade(session: Session, pmids: list[str]) -> set[str]:
    return set(
        session.scalars(
            select(Grade.pmid).where(Grade.pmid.in_(pmids), Grade.rubric_version == RUBRIC_VERSION)
        )
    )


def store_grade(session: Session, o: GradeOutcome) -> None:
    """Insert one grade; a duplicate (pmid, rubric_version, model) is ignored. Caller commits."""
    stmt = insert(Grade).values(
        pmid=o.pmid,
        rubric_version=RUBRIC_VERSION,
        model=o.model,
        input_source=o.input_source,
        **o.data.scores,
        justifications=o.data.justifications,
        summary=o.data.summary,
        why_it_matters=o.data.why_it_matters,
        study_design=o.data.study_design,
        sample_size=o.data.sample_size,
        input_tokens=o.usage.total_input,
        output_tokens=o.usage.output,
    )
    session.execute(stmt.on_conflict_do_nothing())


def _apply(session: Session, result: GradeResult, today: date, stats: GradeStats) -> None:
    if result.cost:
        record_spend(session, today, result.cost)
        stats.usd += result.cost
    if isinstance(result, GradeOutcome):
        store_grade(session, result)
        stats.graded += 1


def _inputs(
    session: Session, pmids: list[str], full_texts: Mapping[str, str] | None = None
) -> dict[str, GradeInput]:
    texts = full_texts or {}
    papers = session.scalars(select(Paper).where(Paper.pmid.in_(pmids)))
    return {p.pmid: GradeInput(p, texts.get(p.pmid)) for p in papers}


def _grade_with_retry(
    session: Session, grader: Grader, item: GradeInput, today: date, stats: GradeStats, tries: int
) -> None:
    for attempt in range(tries):
        if attempt:
            stats.retried += 1
        result = grader.grade_sync(item)
        _apply(session, result, today, stats)
        session.commit()
        if isinstance(result, GradeOutcome):
            return
        log.warning("PMID %s attempt %d failed: %s", item.paper.pmid, attempt + 1, result.reason)
    stats.failed.append(item.paper.pmid)


def grade_sync(
    session: Session,
    grader: Grader,
    pmids: list[str],
    today: date,
    full_texts: Mapping[str, str] | None = None,
) -> GradeStats:
    """Grade papers one synchronous call at a time (CLI and retries). One retry each."""
    stats = GradeStats()
    done = has_current_grade(session, pmids)
    items = _inputs(session, [p for p in pmids if p not in done], full_texts)
    for item in items.values():
        _grade_with_retry(session, grader, item, today, stats, tries=2)
    return stats


def _wait(grader: Grader, batch: GradingBatch, poll: Polling) -> None:
    deadline = poll.clock() + poll.timeout
    while not grader.batch_ended(batch.id):
        if poll.clock() >= deadline:
            raise BatchTimeoutError(f"batch {batch.id} not finished after {poll.timeout:.0f}s")
        poll.sleep(poll.interval)


def _as_sent(batch: GradingBatch, items: dict[str, GradeInput]) -> dict[str, GradeInput]:
    """Label results with what was actually sent, even when resuming without the text."""
    return {
        pmid: GradeInput(
            i.paper,
            i.full_text,
            source="full_text" if batch.input_sources.get(pmid) == "full_text" else "abstract",
        )
        for pmid, i in items.items()
    }


def _to_retry(
    batch: GradingBatch, results: list[GradeResult], items: dict[str, GradeInput]
) -> list[str]:
    """Failed or invalid items, and items the batch never returned."""
    returned = {r.pmid for r in results}
    failed = [r.pmid for r in results if isinstance(r, GradeFailure)]
    return failed + [p for p in batch.pmids if p not in returned and p in items]


def _collect(
    session: Session,
    grader: Grader,
    batch: GradingBatch,
    today: date,
    stats: GradeStats,
    poll: Polling,
    full_texts: Mapping[str, str] | None,
) -> None:
    _wait(grader, batch, poll)
    items = _inputs(session, batch.pmids, full_texts)
    results = grader.batch_results(batch.id, _as_sent(batch, items))
    for r in results:
        _apply(session, r, today, stats)
    batch.status = "collected"
    batch.ended_at = datetime.now(UTC)
    session.commit()

    # Retried once individually, then logged and skipped.
    for pmid in _to_retry(batch, results, items):
        log.warning("PMID %s failed in batch %s; retrying individually", pmid, batch.id)
        stats.retried += 1
        _grade_with_retry(session, grader, items[pmid], today, stats, tries=1)


def grade_batch(
    session: Session,
    grader: Grader,
    pmids: list[str],
    today: date,
    poll: Polling | None = None,
    full_texts: Mapping[str, str] | None = None,
) -> GradeStats:
    """Grade papers via the Message Batches API, resuming any open batch first.

    `full_texts` maps PMID to open-access full text; other papers go from the abstract.
    """
    poll = poll or Polling()
    stats = GradeStats()

    open_batches = session.scalars(
        select(GradingBatch).where(
            GradingBatch.status == "submitted",
            GradingBatch.rubric_version == RUBRIC_VERSION,
            GradingBatch.model == grader.model,
        )
    ).all()
    for batch in open_batches:
        log.info("Resuming open batch %s (%d papers)", batch.id, len(batch.pmids))
        _collect(session, grader, batch, today, stats, poll, full_texts)

    done = has_current_grade(session, pmids)
    items = _inputs(session, [p for p in pmids if p not in done], full_texts)
    if not items:
        return stats

    batch_id = grader.submit_batch(items.values())
    batch = GradingBatch(
        id=batch_id,
        rubric_version=RUBRIC_VERSION,
        model=grader.model,
        pmids=list(items),
        input_sources={pmid: i.input_source for pmid, i in items.items()},
    )
    session.add(batch)
    session.commit()
    stats.submitted = len(items)
    log.info("Submitted batch %s with %d papers", batch_id, len(items))

    _collect(session, grader, batch, today, stats, poll, full_texts)
    return stats
