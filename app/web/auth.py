"""Sign-in by magic link (SPEC.md §11): /login, /auth, /logout.

The emailed link is BASE_URL/auth#<token>. The token sits in the URL fragment, which
browsers never send, so it stays out of access logs; and opening the link only shows a
"Sign in" button whose tap POSTs the token, so mail scanners that open links (even
running scripts) cannot use it up.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.accounts import magic_links
from app.accounts.users import get_by_email, is_onboarded, normalise_email
from app.config import Settings
from app.db.session import get_session
from app.email.base import EmailMessage, Mailer, MailerError, render
from app.web.deps import MailerDep, SettingsDep
from app.web.sessions import CurrentUser, end_session, start_session
from app.web.templating import TEMPLATES

log = logging.getLogger(__name__)
router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def login_link(settings: Settings, token: str) -> str:
    return f"{settings.base_url.rstrip('/')}/auth#{token}"


def _send(mailer: Mailer, message: EmailMessage, user_id: uuid.UUID) -> None:
    try:
        mailer.send(message)
    except MailerError as e:
        log.error("sign-in email to user %s failed: %s", user_id, e)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: CurrentUser) -> Response:
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return TEMPLATES.TemplateResponse(request, "auth/login.html")


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    mailer: MailerDep,
    background: BackgroundTasks,
    email: Annotated[str, Form()] = "",
) -> Response:
    email = normalise_email(email)
    if "@" not in email:
        return TEMPLATES.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Enter your email address.", "email": email},
            status_code=422,
        )
    now = datetime.now(UTC)
    if not magic_links.allow_attempt(session, email, now):
        return TEMPLATES.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Too many sign-in requests. Try again in an hour.", "email": email},
            status_code=429,
        )
    # Same answer whether or not the address has an account (no account enumeration), and
    # the email goes out after the response, so response time does not tell either.
    if (user := get_by_email(session, email)) is not None:
        token = magic_links.issue(session, user, now)
        message = render(
            "magic_link",
            "Sign in to Tell Me Kort",
            user.email,
            link=login_link(settings, token),
            minutes=int(magic_links.LINK_TTL.total_seconds() // 60),
        )
        background.add_task(_send, mailer, message, user.id)
    return TEMPLATES.TemplateResponse(request, "auth/check_email.html", {"email": email})


@router.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "auth/enter.html")


@router.post("/auth")
def auth(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    t: Annotated[str, Form()] = "",
) -> Response:
    user = magic_links.consume(session, t, datetime.now(UTC)) if t else None
    if user is None:
        return TEMPLATES.TemplateResponse(request, "auth/invalid.html", status_code=400)
    response = RedirectResponse("/" if is_onboarded(session, user) else "/onboarding", 303)
    start_session(settings, response, user)
    return response


@router.post("/logout")
def logout() -> Response:
    response = RedirectResponse("/login", status_code=303)
    end_session(response)
    return response
