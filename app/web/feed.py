"""Feed, paper, library and history pages, and in-app feedback (SPEC.md §9, §11)."""

import html
from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.accounts.users import is_onboarded
from app.db.models import FEEDBACK_KINDS, Paper, User
from app.db.session import get_session
from app.domain.criteria import ALL_CRITERIA
from app.domain.edition import edition
from app.feed import feedback, front, queries, suggestions
from app.web.deps import SettingsDep
from app.web.redirects import local_path
from app.web.sessions import CurrentUser, RequiredUser
from app.web.templating import TEMPLATES

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return now().date()


def _not_found(request: Request, user: object) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request, "feed/not_found.html", {"user": user}, status_code=404
    )


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> Response:
    if user is None:
        return TEMPLATES.TemplateResponse(request, "home.html")
    if not is_onboarded(session, user):
        return RedirectResponse("/onboarding", status_code=303)
    items = queries.feed(session, user.id, settings, today())
    context = {
        "user": user,
        "items": items,
        "edition": edition(now(), ZoneInfo(user.timezone), len(items)),
        "beat": front.beat(session, user.id),
        "run": front.latest_run(session),
        "suggestion": suggestions.current_suggestion(session, user.id, settings),
    }
    return TEMPLATES.TemplateResponse(request, "feed/feed.html", context)


@router.post("/suggestion/{choice}")
def answer_suggestion(
    choice: str,
    user: RequiredUser,
    session: SessionDep,
    criterion: Annotated[str, Form()] = "",
) -> Response:
    """Apply or dismiss a weight suggestion; weights only change on an explicit apply."""
    if choice not in ("apply", "dismiss") or criterion not in ALL_CRITERIA:
        return HTMLResponse("Unknown suggestion.", status_code=422)
    (suggestions.apply if choice == "apply" else suggestions.dismiss)(session, user.id, criterion)
    return RedirectResponse("/", status_code=303)


@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request, user: CurrentUser, settings: SettingsDep) -> HTMLResponse:
    """The one-page privacy note (SPEC.md §16); public."""
    return TEMPLATES.TemplateResponse(
        request,
        "privacy.html",
        {"user": user, "contact": settings.admin_email, "email_provider": settings.email_provider},
    )


@router.get("/paper/{pmid}", response_class=HTMLResponse)
def paper_page(
    request: Request,
    pmid: str,
    user: RequiredUser,
    session: SessionDep,
    settings: SettingsDep,
    noted: str = "",
) -> Response:
    item = queries.paper(session, user.id, pmid, settings)
    if item is None:
        return _not_found(request, user)
    return TEMPLATES.TemplateResponse(
        request, "feed/paper.html", {"user": user, "item": item, "noted": noted}
    )


@router.post("/paper/{pmid}/feedback")
def give_feedback(
    request: Request,
    pmid: str,
    user: RequiredUser,
    session: SessionDep,
    settings: SettingsDep,
    kind: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
) -> Response:
    if kind not in FEEDBACK_KINDS:
        return HTMLResponse("Unknown action.", status_code=422)
    # Any stored paper: library and history papers may have lost their current grade.
    if session.get(Paper, pmid) is None:
        return _not_found(request, user)
    feedback.record(session, user.id, pmid, kind, "app", settings)
    return RedirectResponse(local_path(next, f"/paper/{pmid}"), status_code=303)


@router.post("/paper/{pmid}/dispute")
def dispute(
    request: Request,
    pmid: str,
    user: RequiredUser,
    session: SessionDep,
    criterion: Annotated[str, Form()] = "",
    user_score: Annotated[str, Form()] = "",
    comment: Annotated[str, Form()] = "",
) -> Response:
    score = int(user_score) if user_score.strip().isdigit() else None
    try:
        feedback.dispute(session, user.id, pmid, criterion, score, comment)
    except LookupError:
        return _not_found(request, user)
    except ValueError as e:
        return HTMLResponse(f"Not saved: {html.escape(str(e))}.", status_code=422)
    return RedirectResponse(f"/paper/{pmid}?noted={criterion}#scores", status_code=303)


def _shelf_page(request: Request, user: User, session: Session, name: str) -> HTMLResponse:
    entries = queries.shelf(session, user.id, name)
    return TEMPLATES.TemplateResponse(
        request, f"feed/{name}.html", {"user": user, "entries": entries}
    )


@router.get("/library", response_class=HTMLResponse)
def library_page(request: Request, user: RequiredUser, session: SessionDep) -> HTMLResponse:
    return _shelf_page(request, user, session, "library")


@router.get("/history", response_class=HTMLResponse)
def history_page(request: Request, user: RequiredUser, session: SessionDep) -> HTMLResponse:
    return _shelf_page(request, user, session, "history")
