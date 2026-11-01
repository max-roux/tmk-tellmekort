"""Blind calibration grading for the surgeon (SPEC.md §12 step 2). Model scores are never shown.

Open to signed-in admins and users marked `can_calibrate` (`cli.py users add --calibrator`).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.db.models import CalibrationItem, Paper, User
from app.db.session import get_session
from app.domain.criteria import INTRINSIC_CRITERIA
from app.grading.rubric import criterion_guides
from app.jobs.calibration import current_items, save_surgeon_scores
from app.web.sessions import CurrentUser
from app.web.templating import TEMPLATES

router = APIRouter(prefix="/admin/calibrate")

SessionDep = Annotated[Session, Depends(get_session)]


def _gate(request: Request, user: User | None) -> Response | None:
    """A response refusing access, or None when the user may calibrate."""
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not (user.is_admin or user.can_calibrate):
        return TEMPLATES.TemplateResponse(
            request, "calibrate/denied.html", {"user": user}, status_code=403
        )
    return None


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


@router.get("", response_class=HTMLResponse)
def overview(request: Request, session: SessionDep, user: CurrentUser) -> Response:
    if refused := _gate(request, user):
        return refused
    items = current_items(session)
    pmids = [i.pmid for i in items]
    papers = {p.pmid: p for p in session.scalars(select(Paper).where(Paper.pmid.in_(pmids)))}
    return TEMPLATES.TemplateResponse(
        request,
        "calibrate/overview.html",
        {
            "user": user,
            "rows": [(i, papers[i.pmid]) for i in items],
            "done": sum(i.surgeon_scores is not None for i in items),
            "next_url": _next_ungraded(items),
        },
    )


@router.get("/{item_id}", response_class=HTMLResponse)
def item_page(
    request: Request,
    item_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    if refused := _gate(request, user):
        return refused
    items = current_items(session)
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        return RedirectResponse("/admin/calibrate", status_code=303)
    return _render_item(request, session, items, item, item.surgeon_scores or {})


def _form_scores(form: FormData) -> tuple[dict[str, int], str]:
    """Scores given (unanswered criteria left out) and the comment."""
    values = {k: v for k, v in form.items() if isinstance(v, str)}
    scores = {c: int(values[c]) for c in INTRINSIC_CRITERIA if values.get(c, "").isdigit()}
    return scores, values.get("comment", "")


def _incomplete(
    request: Request, session: Session, item_id: uuid.UUID, entered: dict[str, object]
) -> HTMLResponse:
    """The item again, keeping what was entered, with the error shown."""
    items = current_items(session)
    item = next(i for i in items if i.id == item_id)
    return _render_item(request, session, items, item, entered, "Pick a score for every criterion.")


@router.post("/{item_id}")
async def save_item(
    request: Request,
    item_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    if refused := _gate(request, user):
        return refused
    scores, comment = _form_scores(await request.form())
    try:
        save_surgeon_scores(session, item_id, scores, comment)
    except LookupError:
        return RedirectResponse("/admin/calibrate", status_code=303)
    except ValueError:
        return _incomplete(request, session, item_id, {**scores, "comment": comment})
    return RedirectResponse(
        _next_ungraded(current_items(session), after=item_id) or "/admin/calibrate",
        status_code=303,
    )
