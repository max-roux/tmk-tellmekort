"""The reader's choice of edition (SPEC.md §11.2): morning (light), evening (dark) or auto.

Kept in a plain cookie, so it works signed out and needs no schema change. Auto clears
the cookie and the page follows the device's light or dark setting.
"""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.web.redirects import local_path

router = APIRouter()

COOKIE = "theme"
THEMES = ("light", "dark")
MAX_AGE_S = 365 * 24 * 3600


def chosen_theme(request: Request) -> str | None:
    """'light' or 'dark' when the reader picked one; None follows the device."""
    value = request.cookies.get(COOKIE)
    return value if value in THEMES else None


@router.post("/theme")
def set_theme(
    request: Request,
    theme: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
) -> Response:
    if theme not in (*THEMES, "auto"):
        return HTMLResponse("Unknown edition.", status_code=422)
    response = RedirectResponse(local_path(next, "/"), status_code=303)
    if theme == "auto":
        response.delete_cookie(COOKIE, path="/")
    else:
        response.set_cookie(
            COOKIE,
            theme,
            max_age=MAX_AGE_S,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            path="/",
        )
    return response
