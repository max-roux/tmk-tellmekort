"""Signed-link access to the calibration pages, until admin login lands (milestone 6).

The token travels in the URL fragment, which browsers never send to the server, so it
does not end up in access logs. The entry page posts it back; the server then keeps it
in an httpOnly cookie. Nothing is stored server-side.
"""

from fastapi import Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import Settings

COOKIE = "calibrate_access"
MAX_AGE_S = 30 * 24 * 3600
_SALT = "calibrate-access"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def make_token(settings: Settings) -> str:
    return _serializer(settings).dumps({"scope": "calibrate"})


def make_link(settings: Settings) -> str:
    return f"{settings.base_url.rstrip('/')}/admin/calibrate/enter#{make_token(settings)}"


def token_valid(settings: Settings, token: str | None) -> bool:
    if not token:
        return False
    try:
        data = _serializer(settings).loads(token, max_age=MAX_AGE_S)
    except BadSignature:  # includes SignatureExpired
        return False
    return isinstance(data, dict) and data.get("scope") == "calibrate"


def has_access(settings: Settings, request: Request) -> bool:
    return token_valid(settings, request.cookies.get(COOKIE))


def grant(settings: Settings, response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=MAX_AGE_S,
        httponly=True,
        secure=settings.base_url.startswith("https://"),
        samesite="lax",
        path="/admin/calibrate",
    )
