"""Operator CLI. Commands are added per milestone (SPEC.md §18)."""

import logging
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
from app.jobs.grade_papers import grade_batch, grade_sync, ungraded_pmids
from app.jobs.weekly_ingest import ingest as run_ingest
from app.sources.pubmed import PubMedClient, load_specialty_query

cli = typer.Typer(no_args_is_help=True, help="Maxfac Paper Recommender operator CLI.")


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
    if not settings.anthropic_api_key:
        typer.echo("ANTHROPIC_API_KEY is not set (add it to .env).", err=True)
        raise typer.Exit(1)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    grader = Grader(client, model=settings.anthropic_model, effort=settings.grading_effort)
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
