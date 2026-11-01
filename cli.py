"""Operator CLI. Commands are added per milestone (SPEC.md §18)."""

import logging
import random
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import anthropic
import typer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Grade
from app.db.session import get_engine
from app.domain.criteria import INTRINSIC_CRITERIA
from app.embeddings.voyage import VoyageEmbedder
from app.grading.grader import Grader
from app.grading.rubric import RUBRIC_VERSION
from app.jobs.calibration import (
    CalibrationSetExistsError,
    calibration_report,
    create_sample,
    grade_set,
)
from app.jobs.embed_papers import embed_papers
from app.jobs.full_text import fetch_full_texts
from app.jobs.grade_papers import grade_batch, grade_sync
from app.jobs.narrow_candidates import load_anchor, narrow, selected_ungraded, week_of
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


def _pubmed() -> PubMedClient:
    settings = get_settings()
    return PubMedClient(
        api_key=settings.ncbi_api_key, email=settings.ncbi_email, tool=settings.ncbi_tool
    )


def _embedder() -> VoyageEmbedder:
    settings = get_settings()
    if not settings.voyage_api_key:
        typer.echo("VOYAGE_API_KEY is not set (add it to .env).", err=True)
        raise typer.Exit(1)
    return VoyageEmbedder(api_key=settings.voyage_api_key, model=settings.embedding_model)


def _window(days: int, backfill: bool, until: datetime | None) -> tuple[date, date]:
    settings = get_settings()
    end = until.date() if until else datetime.now(UTC).date()
    span = settings.active_window_days if backfill else days
    return end - timedelta(days=span - 1), end


DaysOpt = Annotated[int, typer.Option(help="Entrez-date window, ending on --until.")]
BackfillOpt = Annotated[
    bool, typer.Option(help="Cover the whole active window (ACTIVE_WINDOW_DAYS).")
]
UntilOpt = Annotated[
    datetime | None, typer.Option(formats=["%Y-%m-%d"], help="Last day (default today UTC).")
]


@cli.command()
def ingest(days: DaysOpt = 7, backfill: BackfillOpt = False, until: UntilOpt = None) -> None:
    """Fetch papers from PubMed with the specialty query and store them."""
    start, end = _window(days, backfill, until)
    typer.echo(f"Ingesting entrez dates {start} .. {end}")
    with _pubmed() as client, Session(get_engine()) as session:
        stats = run_ingest(session, client, load_specialty_query(), start, end)
    typer.echo(
        f"Found {stats.found}, already stored {stats.already_stored}, "
        f"stored {stats.stored}, skipped (no abstract) {stats.skipped_no_abstract}."
    )


@cli.command()
def embed() -> None:
    """Embed every paper that has no embedding from the current model."""
    embedder = _embedder()
    with Session(get_engine()) as session:
        stats = embed_papers(session, embedder)
    embedder.close()
    typer.echo(f"Embedded {stats.embedded} papers ({stats.tokens} tokens).")


@cli.command("narrow")
def narrow_cmd(
    days: DaysOpt = 7,
    backfill: BackfillOpt = False,
    until: UntilOpt = None,
    limit: Annotated[
        int | None, typer.Option(help="Papers to select (default GRADE_LIMIT_PER_WEEK).")
    ] = None,
) -> None:
    """Score papers in the window against the specialty anchor and select the top N."""
    settings = get_settings()
    start, end = _window(days, backfill, until)
    embedder = _embedder()
    week = week_of(datetime.now(UTC).date())
    with Session(get_engine()) as session:
        stats = narrow(
            session,
            embedder,
            start=start,
            end=end,
            week=week,
            limit=limit or settings.grade_limit_per_week,
            anchor_text=load_anchor(),
        )
    embedder.close()
    typer.echo(
        f"Week of {week}: {stats.candidates} candidates ({start} .. {end}), "
        f"{stats.selected} selected for grading."
    )
    if stats.missing_embeddings:
        typer.echo(f"{stats.missing_embeddings} papers in the window have no embedding: run embed.")


@cli.command()
def grade(
    pmids: Annotated[list[str] | None, typer.Argument(help="PMIDs to grade synchronously.")] = None,
    batch: Annotated[
        bool, typer.Option(help="Grade papers selected by narrow via the Batches API.")
    ] = False,
    limit: Annotated[int | None, typer.Option(help="Max papers for --batch.")] = None,
) -> None:
    """Grade papers with the current rubric. Already-graded papers are skipped."""
    if not pmids and not batch:
        raise typer.BadParameter("give PMIDs, or --batch")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    grader = _grader()
    today = datetime.now(UTC).date()
    with Session(get_engine()) as session, _pubmed() as pubmed:
        todo = selected_ungraded(session, limit) if batch else (pmids or [])
        texts = fetch_full_texts(session, pubmed, todo, settings.fulltext_max_tokens)
        typer.echo(
            f"Grading {len(todo)} papers with rubric v{RUBRIC_VERSION} "
            f"({len(texts)} from open-access full text)..."
        )
        if batch:
            stats = grade_batch(session, grader, todo, today, full_texts=texts)
        else:
            stats = grade_sync(session, grader, todo, today, full_texts=texts)
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
