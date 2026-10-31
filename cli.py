"""Operator CLI. Commands are added per milestone (SPEC.md §18)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import typer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_engine
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
