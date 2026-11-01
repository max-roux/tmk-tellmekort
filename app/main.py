from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_session
from app.web import actions, auth, calibrate, feed, onboarding
from app.web.sessions import LoginRequiredError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if problems := settings.production_problems():
        raise RuntimeError("Refusing to start: " + "; ".join(problems))
    app = FastAPI(title="Maxfac Paper Recommender")
    app.include_router(auth.router)
    app.include_router(onboarding.router)
    app.include_router(calibrate.router)
    app.include_router(feed.router)
    app.include_router(actions.router)

    @app.exception_handler(LoginRequiredError)
    def _login_required(request: Request, exc: LoginRequiredError) -> Response:
        return RedirectResponse("/login", status_code=303)

    @app.get("/healthz")
    def healthz(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"status": "degraded", "db": "unreachable"}, status_code=503)
        return JSONResponse({"status": "ok", "db": "ok"})

    return app


app = create_app()
