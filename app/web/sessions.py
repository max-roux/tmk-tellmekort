"""Signed session cookie (SPEC.md §11): 30 days, httpOnly, secure on https.

The cookie carries only the user id, signed with SECRET_KEY. Deleting the user ends
the session; there is no server-side session store.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_session

COOKIE = "session"
MAX_AGE_S = 30 * 24 * 3600
_SALT = "session"


class LoginRequiredError(Exception):
    """Raised by `require_user`; the app turns it into a redirect to /login."""


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def start_session(settings: Settings, response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE,
        _serializer(settings).dumps({"uid": str(user.id)}),
        max_age=MAX_AGE_S,
        httponly=True,
        secure=settings.base_url.startswith("https://"),
        samesite="lax",
        path="/",
    )


def end_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def session_user_id(settings: Settings, request: Request) -> uuid.UUID | None:
    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    try:
        data = _serializer(settings).loads(raw, max_age=MAX_AGE_S)
        return uuid.UUID(data["uid"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


def current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User | None:
    uid = session_user_id(settings, request)
    return session.get(User, uid) if uid else None


def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
    if user is None:
        raise LoginRequiredError
    return user


CurrentUser = Annotated[User | None, Depends(current_user)]
RequiredUser = Annotated[User, Depends(require_user)]
