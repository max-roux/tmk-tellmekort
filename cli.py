"""Operator CLI. Commands are added per milestone (SPEC.md §18)."""

import logging
import random
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import anthropic
import typer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.accounts import magic_links
from app.accounts.users import add_user, get_by_email, is_onboarded
from app.config import get_settings
from app.db.models import Grade, ProfileVector, User
from app.db.session import get_engine
from app.domain.criteria import INTRINSIC_CRITERIA
from app.email import mailer_for
from app.email.outbox import DEFAULT_DIR as OUTBOX_DIR
from app.email.outbox import OutboxMailer
from app.embeddings.base import EmbeddingError
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
from app.jobs.narrow_candidates import (
    load_anchor,
    narrow,
    selected_ungraded,
    user_references,
    week_of,
)
from app.jobs.regrade import regrade
from app.jobs.send_due_emails import preview, send_due
from app.jobs.weekly_ingest import ingest as run_ingest
from app.jobs.weekly_pipeline import Clients, run_weekly
from app.profiles.service import coefficients, embed_topics, refresh_all_profiles
from app.sources.pubmed import PubMedClient, load_specialty_query
from app.web.auth import login_link

cli = typer.Typer(no_args_is_help=True, help="Tell Me Kort operator CLI.")
calibrate = typer.Typer(
    no_args_is_help=True, help="Rubric calibration with the surgeon (SPEC §12)."
)
cli.add_typer(calibrate, name="calibrate")
users = typer.Typer(no_args_is_help=True, help="User accounts (no self-serve sign-up).")
cli.add_typer(users, name="users")


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


# Two weeks, so papers entered on the previous run's day after it ran are still caught;
# already stored papers are skipped, so the overlap costs only a search.
INGEST_DAYS = 14

DaysOpt = Annotated[int, typer.Option(help="Entrez-date window, ending on --until.")]
BackfillOpt = Annotated[
    bool, typer.Option(help="Cover the whole active window (ACTIVE_WINDOW_DAYS).")
]
UntilOpt = Annotated[
    datetime | None, typer.Option(formats=["%Y-%m-%d"], help="Last day (default today UTC).")
]


@cli.command()
def ingest(
    days: DaysOpt = INGEST_DAYS, backfill: BackfillOpt = False, until: UntilOpt = None
) -> None:
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
    """Embed papers and topics lacking a current embedding, then refresh profile vectors."""
    embedder = _embedder()
    try:
        with Session(get_engine()) as session:
            stats = embed_papers(session, embedder)
            topics = embed_topics(session, embedder)
            profiles = refresh_all_profiles(session, embedder.model, coefficients(get_settings()))
    except EmbeddingError as e:
        # Chunks already embedded are committed; re-running resumes from there.
        typer.echo(f"Embedding stopped: {e}", err=True)
        raise typer.Exit(1) from None
    finally:
        embedder.close()
    typer.echo(
        f"Embedded {stats.embedded} papers ({stats.tokens} tokens) and {topics} topics; "
        f"{profiles} users have a profile vector."
    )


@cli.command("narrow")
def narrow_cmd(
    limit: Annotated[
        int | None, typer.Option(help="Papers to select (default GRADE_LIMIT_PER_WEEK).")
    ] = None,
) -> None:
    """Score papers not yet considered against the anchor and users; select the top N."""
    settings = get_settings()
    embedder = _embedder()
    today = datetime.now(UTC).date()
    week = week_of(today)
    with Session(get_engine()) as session:
        refs = user_references(session, embedder.model)
        stats = narrow(
            session,
            embedder,
            since=today - timedelta(days=settings.active_window_days),
            week=week,
            limit=limit or settings.grade_limit_per_week,
            anchor_text=load_anchor(),
            profile_vectors=refs.vectors,
            always_include=refs.seeds,
        )
    embedder.close()
    typer.echo(
        f"Week of {week}: {stats.candidates} new candidates, "
        f"{stats.selected} selected for grading "
        f"({len(refs.vectors)} user vectors, {len(refs.seeds)} seed papers)."
    )
    if stats.missing_embeddings:
        typer.echo(f"{stats.missing_embeddings} new papers have no embedding: run embed.")


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


@users.command("add")
def users_add(
    email: str,
    name: Annotated[str, typer.Option(help="Display name.")] = "",
    admin: Annotated[bool, typer.Option(help="Can open /admin pages.")] = False,
    calibrator: Annotated[
        bool, typer.Option(help="Can blind-grade the calibration set (the surgeon).")
    ] = False,
) -> None:
    """Create a user, or update the name and grant flags of an existing one."""
    with Session(get_engine()) as session:
        try:
            user = add_user(session, email, name=name, is_admin=admin, can_calibrate=calibrator)
        except ValueError as e:
            raise typer.BadParameter(str(e)) from None
        roles = [
            r for r, on in (("admin", user.is_admin), ("calibrator", user.can_calibrate)) if on
        ]
        typer.echo(f"{user.email}{f' ({", ".join(roles)})' if roles else ''}: ready to sign in.")


@users.command("list")
def users_list() -> None:
    """List users with their onboarding state."""
    with Session(get_engine()) as session:
        for u in session.scalars(select(User).order_by(User.created_at)):
            state = "onboarded" if is_onboarded(session, u) else "not onboarded"
            vector = "profile vector" if session.get(ProfileVector, u.id) else "no profile vector"
            admin = ", admin" if u.is_admin else ""
            admin += ", calibrator" if u.can_calibrate else ""
            typer.echo(f"{u.email}  ({state}, {vector}{admin})")


@users.command("link")
def users_link(email: str) -> None:
    """Print a one-time sign-in link (15 minutes) without sending email."""
    with Session(get_engine()) as session:
        user = get_by_email(session, email)
        if user is None:
            typer.echo(f"No user {email}. Add one with: cli.py users add {email}", err=True)
            raise typer.Exit(1)
        token = magic_links.issue(session, user, datetime.now(UTC))
    typer.echo(login_link(get_settings(), token))


def _production_ready() -> None:
    if problems := get_settings().production_problems():
        typer.echo("Refusing to send: " + "; ".join(problems), err=True)
        raise typer.Exit(1)


@cli.command()
def weekly() -> None:
    """Run the whole weekly pipeline: ingest, embed, narrow, full text, grade (Sunday cron)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _production_ready()
    settings = get_settings()
    embedder = _embedder()
    with Session(get_engine()) as session, _pubmed() as pubmed:
        clients = Clients(pubmed, embedder, _grader(), mailer_for(settings))
        # Read inside the session: committing expired the run, so it can't load afterwards.
        stats = run_weekly(session, settings, clients, datetime.now(UTC)).stats
    embedder.close()
    grade = stats["grade"]
    typer.echo(
        f"Done: stored {stats['ingest']['stored']} papers, graded {grade['graded']} "
        f"(dropped by the cap {grade['dropped']}), ${grade['month_usd']:.2f} spent this month."
    )


@cli.command("regrade")
def regrade_cmd(
    window: Annotated[
        int | None, typer.Option(help="Days back to regrade (default ACTIVE_WINDOW_DAYS).")
    ] = None,
) -> None:
    """Grade papers in the window that only have grades from older rubric versions."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    days = window or settings.active_window_days
    with Session(get_engine()) as session, _pubmed() as pubmed:
        stats = regrade(
            session,
            pubmed,
            _grader(),
            mailer_for(settings),
            settings,
            datetime.now(UTC).date(),
            window_days=days,
        )
    typer.echo(
        f"Rubric v{RUBRIC_VERSION}, last {days} days: {stats['todo']} stale, graded "
        f"{stats['graded']} (cut by the cap {stats['dropped']}), ${stats['usd']:.2f}."
    )


@cli.command("send-due")
def send_due_cmd() -> None:
    """Send the weekly email to every user whose slot has passed (run hourly)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _production_ready()
    settings = get_settings()
    with Session(get_engine()) as session:
        stats = send_due(session, settings, mailer_for(settings), datetime.now(UTC))
    typer.echo(f"Sent {stats.sent} ({stats.quiet} quiet weeks), failed {stats.failed}.")
    if stats.failed:
        raise typer.Exit(1)


@cli.command("send-test")
def send_test(email: str) -> None:
    """Write the email EMAIL would get now to var/outbox, without sending or recording it."""
    with Session(get_engine()) as session:
        user = get_by_email(session, email)
        if user is None:
            typer.echo(f"No user {email}.", err=True)
            raise typer.Exit(1)
        message = preview(session, user, get_settings(), datetime.now(UTC))
    OutboxMailer().send(message)
    typer.echo(f"Wrote '{message.subject}' to {OUTBOX_DIR}.")


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
