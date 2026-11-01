"""Blind calibration grading for the surgeon (SPEC.md §12 step 2). Model scores are never shown."""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import CalibrationItem, Paper
from app.db.session import get_session
from app.domain.criteria import INTRINSIC_CRITERIA
from app.grading.rubric import criterion_guides
from app.jobs.calibration import current_items, save_surgeon_scores
from app.web import access

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
router = APIRouter(prefix="/admin/calibrate")

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _denied(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "calibrate/denied.html", status_code=403)


def _render_item(
    request: Request,
    session: Session,
    items: list[CalibrationItem],
    item: CalibrationItem,
    scores: dict[str, object],
    error: str | None = None,
) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "calibrate/item.html",
        {
            "item": item,
            "paper": session.get(Paper, item.pmid),
            "position": items.index(item) + 1,
            "total": len(items),
            "guides": criterion_guides(),
            "scores": scores,
            "error": error,
        },
        status_code=422 if error else 200,
    )


def _next_ungraded(items: list[CalibrationItem], after: uuid.UUID | None = None) -> str | None:
    """URL of the next item without surgeon scores, wrapping around after `after`."""
    ids = [i.id for i in items]
    start = ids.index(after) + 1 if after in ids else 0
    for item in items[start:] + items[:start]:
        if item.surgeon_scores is None:
            return f"/admin/calibrate/{item.id}"
    return None


@router.get("/enter", response_class=HTMLResponse)
def enter_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "calibrate/enter.html")


@router.post("/enter")
def enter(request: Request, settings: SettingsDep, t: Annotated[str, Form()] = "") -> Response:
    if not access.token_valid(settings, t):
        return _denied(request)
    response = RedirectResponse("/admin/calibrate", status_code=303)
    access.grant(settings, response, t)
    return response


@router.get("", response_class=HTMLResponse)
def overview(request: Request, session: SessionDep, settings: SettingsDep) -> Response:
    if not access.has_access(settings, request):
        return _denied(request)
    items = current_items(session)
    pmids = [i.pmid for i in items]
    papers = {p.pmid: p for p in session.scalars(select(Paper).where(Paper.pmid.in_(pmids)))}
    return TEMPLATES.TemplateResponse(
        request,
        "calibrate/overview.html",
        {
            "rows": [(i, papers[i.pmid]) for i in items],
            "done": sum(i.surgeon_scores is not None for i in items),
            "next_url": _next_ungraded(items),
        },
    )


@router.get("/{item_id}", response_class=HTMLResponse)
def item_page(
    request: Request, item_id: uuid.UUID, session: SessionDep, settings: SettingsDep
) -> Response:
    if not access.has_access(settings, request):
        return _denied(request)
    items = current_items(session)
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        return RedirectResponse("/admin/calibrate", status_code=303)
    return _render_item(request, session, items, item, item.surgeon_scores or {})


@router.post("/{item_id}")
async def save_item(
    request: Request, item_id: uuid.UUID, session: SessionDep, settings: SettingsDep
) -> Response:
    if not access.has_access(settings, request):
        return _denied(request)
    form = await request.form()
    scores: dict[str, int] = {}
    for c in INTRINSIC_CRITERIA:
        raw = form.get(c)
        if isinstance(raw, str) and raw.isdigit():
            scores[c] = int(raw)
    comment = form.get("comment")
    comment = comment if isinstance(comment, str) else ""
    try:
        save_surgeon_scores(session, item_id, scores, comment)
    except LookupError:
        return RedirectResponse("/admin/calibrate", status_code=303)
    except ValueError:
        items = current_items(session)
        item = next(i for i in items if i.id == item_id)
        scores_shown: dict[str, object] = {**scores, "comment": comment}
        return _render_item(
            request, session, items, item, scores_shown, "Pick a score for every criterion."
        )
    return RedirectResponse(
        _next_ungraded(current_items(session), after=item_id) or "/admin/calibrate",
        status_code=303,
    )
