"""Settings (SPEC.md §11): weekly email day, time and timezone; account deletion (§16)."""

from typing import Annotated
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.accounts.users import delete_user
from app.db.models import User
from app.db.session import get_session
from app.domain.schedule import ScheduleError, parse_schedule
from app.web.sessions import RequiredUser, end_session
from app.web.templating import TEMPLATES

router = APIRouter(prefix="/settings")

SessionDep = Annotated[Session, Depends(get_session)]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TIMEZONES = sorted(z for z in available_timezones() if "/" in z and not z.startswith("Etc/"))


def _page(
    request: Request, user: User, error: str | None = None, saved: bool = False
) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "settings.html",
        {
            "user": user,
            "weekdays": WEEKDAYS,
            "timezones": TIMEZONES,
            "error": error,
            "saved": saved,
            "nav": "settings",
        },
        status_code=422 if error else 200,
    )


@router.get("", response_class=HTMLResponse)
def settings_page(request: Request, user: RequiredUser, saved: str = "") -> HTMLResponse:
    return _page(request, user, saved=bool(saved))


@router.post("", response_class=HTMLResponse)
async def save(request: Request, user: RequiredUser, session: SessionDep) -> Response:
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    try:
        schedule = parse_schedule(form)
    except ScheduleError as e:
        return _page(request, user, error=str(e))
    user.send_weekday, user.send_local_time = schedule.weekday, schedule.at
    user.timezone = schedule.timezone
    session.commit()
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/delete", response_class=HTMLResponse)
def delete_account(
    request: Request,
    user: RequiredUser,
    session: SessionDep,
    confirm: Annotated[str, Form()] = "",
) -> Response:
    if confirm.strip().lower() != "delete":
        return _page(request, user, error='Type "delete" to confirm.')
    delete_user(session, user)
    response = RedirectResponse("/", status_code=303)
    end_session(response)
    return response
