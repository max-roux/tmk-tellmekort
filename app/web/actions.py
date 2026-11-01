"""One-tap email actions (SPEC.md §10.4): GET /a renders a page, POST /a records."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.models import EmailSend, User
from app.db.session import get_session
from app.email.actions import read_token
from app.feed import feedback
from app.web.deps import SettingsDep
from app.web.templating import TEMPLATES

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
LABELS = {"like": "Liked", "read": "Marked as read", "not_for_me": "Removed from your feed"}


@router.get("/a", response_class=HTMLResponse)
def action_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "actions/enter.html")


@router.post("/a", response_class=HTMLResponse)
def act(
    request: Request, session: SessionDep, settings: SettingsDep, t: Annotated[str, Form()] = ""
) -> HTMLResponse:
    action = read_token(settings, t)
    send = session.get(EmailSend, action.send_id) if action else None
    if action is None or send is None or send.user_id != action.user_id:
        return TEMPLATES.TemplateResponse(request, "actions/invalid.html", status_code=400)
    feedback.record(session, action.user_id, action.pmid, action.action, "email", settings, send.id)
    user = session.get(User, action.user_id)
    return TEMPLATES.TemplateResponse(
        request,
        "actions/saved.html",
        {"label": LABELS[action.action], "pmid": action.pmid, "name": user.name if user else ""},
    )
