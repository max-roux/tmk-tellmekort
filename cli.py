"""Operator CLI. Commands are added per milestone (SPEC.md §18)."""

import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Annotated

import anthropic
import typer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Grade
from app.db.session import get_engine
from app.domain.criteria import INTRINSIC_CRITERIA
from app.grading.grader import Grader
from app.grading.rubric import RUBRIC_VERSION
from app.jobs.calibration import (
    CalibrationSetExistsError,
    calibration_report,
    create_sample,
    grade_set,
)
from app.jobs.grade_papers import grade_batch, grade_sync, ungraded_pmids
from app.jobs.weekly_ingest import ingest as run_ingest
from app.sources.pubmed import PubMedClient, load_specialty_query
from app.web.access import make_link

cli = typer.Typer(no_args_is_help=True, help="Maxfac Paper Recommender operator CLI.")
calibrate = typer.Typer(
    no_args_is_help=True, help="Rubric calibration with the surgeon (SPEC §12)."
)
cli.add_typer(calibrate, name="calibrate")


def _grader() -> Grader:
    settings = get_settings()
    if not settings.anthropic_api_key:
        typer.echo("ANTHROPIC_API_KEY is not set (add it to .env).", err=True)
        raise typer.Exit(1)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return Grader(client, model=settings.anthropic_model, effort=settings.grading_effort)


@cli.command()
def ingest(
    days: Annotated[int, typer.Option(help="Entrez-date window, ending on --until.")] = 7,
    backfill: Annotated[
        bool, typer.Option(help="Fetch the whole active window (ACTIVE_WINDOW_DAYS).")
    ] = False,
    until: Annotated[
        datetime | None, typer.Option(formats=["%Y-%m-%d"], help="Last day (default today UTC).")
    ] = None,
) -> None:
    """Fetch papers from PubMed with the specialty query and store them."""
    settings = get_settings()
    end = until.date() if until else datetime.now(UTC).date()
    span = settings.active_window_days if backfill else days
    start = end - timedelta(days=span - 1)
    typer.echo(f"Ingesting entrez dates {start} .. {end}")
    client = PubMedClient(
        api_key=settings.ncbi_api_key, email=settings.ncbi_email, tool=settings.ncbi_tool
    )
    with client, Session(get_engine()) as session:
        stats = run_ingest(session, client, load_specialty_query(), start, end)
    typer.echo(
        f"Found {stats.found}, already stored {stats.already_stored}, "
        f"stored {stats.stored}, skipped (no abstract) {stats.skipped_no_abstract}."
    )


@cli.command()
def grade(
    pmids: Annotated[list[str] | None, typer.Argument(help="PMIDs to grade synchronously.")] = None,
    batch: Annotated[
        bool, typer.Option(help="Grade the newest ungraded papers via the Batches API.")
    ] = False,
    limit: Annotated[
        int | None, typer.Option(help="Max papers for --batch (default GRADE_LIMIT_PER_WEEK).")
    ] = None,
) -> None:
    """Grade papers with the current rubric. Already-graded papers are skipped."""
    if not pmids and not batch:
        raise typer.BadParameter("give PMIDs, or --batch")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    grader = _grader()
    today = datetime.now(UTC).date()
    with Session(get_engine()) as session:
        if batch:
            todo = ungraded_pmids(session, limit or settings.grade_limit_per_week)
            typer.echo(f"Batch-grading {len(todo)} papers with rubric v{RUBRIC_VERSION}...")
            stats = grade_batch(session, grader, todo, today)
        else:
            stats = grade_sync(session, grader, pmids or [], today)
            for g in session.scalars(
                select(Grade).where(
                    Grade.pmid.in_(pmids or []), Grade.rubric_version == RUBRIC_VERSION
                )
            ):
                typer.echo(f"\nPMID {g.pmid} ({g.study_design}, graded from {g.input_source})")
                for c in INTRINSIC_CRITERIA:
                    typer.echo(f"  {c:<21} {getattr(g, c)}  {g.justifications[c]}")
                typer.echo(f"  summary: {g.summary}\n  why it matters: {g.why_it_matters}")
    typer.echo(
        f"\nGraded {stats.graded}, retried {stats.retried}, failed {len(stats.failed)}"
        f"{' ' + str(stats.failed) if stats.failed else ''}, cost ${stats.usd:.4f}."
    )


@calibrate.command("sample")
def calibrate_sample(
    n: Annotated[int, typer.Option(help="Number of papers.")] = 20,
    seed: Annotated[int | None, typer.Option(help="Random seed, for a reproducible pick.")] = None,
    replace: Annotated[bool, typer.Option(help="Discard the existing set first.")] = False,
) -> None:
    """Pick recent papers stratified by study design as the calibration set."""
    settings = get_settings()
    with Session(get_engine()) as session:
        try:
            pmids = create_sample(
                session,
                n,
                datetime.now(UTC).date(),
                random.Random(seed),
                window_days=settings.active_window_days,
                replace=replace,
            )
        except CalibrationSetExistsError:
            typer.echo("A calibration set already exists. Use --replace to start over.", err=True)
            raise typer.Exit(1) from None
    typer.echo(f"Picked {len(pmids)} papers. Next: uv run python cli.py calibrate grade")


@calibrate.command("grade")
def calibrate_grade() -> None:
    """Grade the set with the current rubric (creating rows for a new rubric version)."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    grader = _grader()
    with Session(get_engine()) as session:
        stats = grade_set(session, grader, datetime.now(UTC).date())
    typer.echo(
        f"Rubric v{RUBRIC_VERSION}: {stats.with_model_scores}/{stats.items} papers have model "
        f"scores (graded {stats.grading.graded} now, cost ${stats.grading.usd:.4f})."
    )


@calibrate.command("link")
def calibrate_link() -> None:
    """Print the private link to the blind-grading page (valid 30 days)."""
    typer.echo(make_link(get_settings()))


@calibrate.command("report")
def calibrate_report(
    version: Annotated[int, typer.Option(help="Rubric version.")] = RUBRIC_VERSION,
    top: Annotated[int, typer.Option(help="Biggest disagreements to show.")] = 5,
) -> None:
    """Agreement between surgeon and model per criterion, and the launch-bar verdict."""
    with Session(get_engine()) as session:
        report, rows = calibration_report(session, version)
    typer.echo(f"Rubric v{version}: {report.n} papers scored by both surgeon and model.\n")
    if not report.n:
        return
    typer.echo(f"{'criterion':<22}{'exact':>7}{'±1':>7}{'kappa':>8}  launch bar")
    for c in report.criteria:
        kappa = f"{c.kappa:.2f}" if c.kappa is not None else "n/a"
        mark = "met" if c.meets_launch_bar else "NOT met"
        typer.echo(f"{c.criterion:<22}{c.exact:>7.0%}{c.within_one:>7.0%}{kappa:>8}  {mark}")
    verdict = "MET" if report.meets_launch_bar else "NOT MET"
    typer.echo(f"\nLaunch bar (±1 ≥ 80% everywhere, ≥ 90% proof strength): {verdict}")
    for d in report.disagreements[:top]:
        if not d.total_gap:
            break
        row = rows[d.pmid]
        typer.echo(f"\nPMID {d.pmid} (total gap {d.total_gap}): {row.title}")
        for crit, gap in d.gaps.items():
            if gap:
                typer.echo(
                    f"  {crit:<21} surgeon {row.surgeon[crit]}  model {row.model[crit]}  "
                    f"{row.justifications.get(crit, '')}"
                )
        if comment := row.surgeon.get("comment"):
            typer.echo(f"  surgeon comment: {comment}")


@cli.command("check-db")
def check_db() -> None:
    """Connect to the database and report the pgvector version."""
    with get_engine().connect() as conn:
        version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    if version is None:
        typer.echo("Connected, but pgvector is not installed. Run: uv run alembic upgrade head")
        raise typer.Exit(1)
    typer.echo(f"Connected. pgvector {version}.")


@cli.callback()
def main() -> None:
    pass


if __name__ == "__main__":
    cli()
