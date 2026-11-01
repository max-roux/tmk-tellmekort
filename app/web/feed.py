"""Feed, paper, library and history pages, and in-app feedback (SPEC.md §9, §11)."""

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.accounts.users import is_onboarded
from app.db.models import FEEDBACK_KINDS, Paper, User
from app.db.session import get_session
from app.feed import feedback, queries
from app.web.deps import SettingsDep
from app.web.sessions import CurrentUser, RequiredUser
from app.web.templating import TEMPLATES

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def today() -> date:
    return datetime.now(UTC).date()


def _local_path(target: str, fallback: str) -> str:
    """Only same-site paths, so `next` cannot send the user elsewhere."""
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return fallback


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
    return TEMPLATES.TemplateResponse(
        request, "feed/feed.html", {"user": user, "items": items, "nav": "feed"}
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
    return RedirectResponse(_local_path(next, f"/paper/{pmid}"), status_code=303)


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
        return HTMLResponse(f"Not saved: {e}.", status_code=422)
    return RedirectResponse(f"/paper/{pmid}?noted={criterion}#scores", status_code=303)


def _shelf_page(request: Request, user: User, session: Session, name: str) -> HTMLResponse:
    entries = queries.shelf(session, user.id, name)
    return TEMPLATES.TemplateResponse(
        request, f"feed/{name}.html", {"user": user, "entries": entries, "nav": name}
    )


@router.get("/library", response_class=HTMLResponse)
def library_page(request: Request, user: RequiredUser, session: SessionDep) -> HTMLResponse:
    return _shelf_page(request, user, session, "library")


@router.get("/history", response_class=HTMLResponse)
def history_page(request: Request, user: RequiredUser, session: SessionDep) -> HTMLResponse:
    return _shelf_page(request, user, session, "history")
