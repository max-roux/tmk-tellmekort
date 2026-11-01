from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.accounts.users import is_onboarded
from app.config import Settings, get_settings
from app.db.session import get_session
from app.web import auth, calibrate, onboarding
from app.web.sessions import CurrentUser, LoginRequiredError
from app.web.templating import TEMPLATES


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if problems := settings.production_problems():
        raise RuntimeError("Refusing to start: " + "; ".join(problems))
    app = FastAPI(title="Maxfac Paper Recommender")
    app.include_router(auth.router)
    app.include_router(onboarding.router)
    app.include_router(calibrate.router)

    @app.exception_handler(LoginRequiredError)
    def _login_required(request: Request, exc: LoginRequiredError) -> Response:
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def home(
        request: Request, user: CurrentUser, session: Annotated[Session, Depends(get_session)]
    ) -> Response:
        if user is None:
            return TEMPLATES.TemplateResponse(request, "home.html")
        if not is_onboarded(session, user):
            return RedirectResponse("/onboarding", status_code=303)
        # The ranked feed replaces this page in milestone 7.
        return TEMPLATES.TemplateResponse(request, "welcome.html", {"user": user})

    @app.get("/healthz")
    def healthz(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"status": "degraded", "db": "unreachable"}, status_code=503)
        return JSONResponse({"status": "ok", "db": "ok"})

    return app


app = create_app()
