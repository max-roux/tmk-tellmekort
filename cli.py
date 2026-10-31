"""Operator CLI. Commands are added per milestone (SPEC.md §18)."""

import typer
from sqlalchemy import text

from app.db.session import get_engine

cli = typer.Typer(no_args_is_help=True, help="Maxfac Paper Recommender operator CLI.")


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
