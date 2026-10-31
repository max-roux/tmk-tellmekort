from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_session

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "web" / "templates")


def create_app() -> FastAPI:
    app = FastAPI(title="Maxfac Paper Recommender")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "home.html")

    @app.get("/healthz")
    def healthz(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"status": "degraded", "db": "unreachable"}, status_code=503)
        return JSONResponse({"status": "ok", "db": "ok"})

    return app


app = create_app()
