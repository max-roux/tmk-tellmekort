"""Admin dashboard (SPEC.md §11): pipeline runs, spend vs cap, disputes, calibration."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Grade, Paper, PipelineRun, ScoreDispute, User
from app.db.session import get_session
from app.grading.cost import month_spend
from app.grading.rubric import criterion_labels
from app.jobs.calibration import calibration_report
from app.jobs.send_due_emails import preview
from app.web.deps import MailerDep, SettingsDep
from app.web.sessions import CurrentUser, gate
from app.web.templating import TEMPLATES

router = APIRouter(prefix="/admin")

SessionDep = Annotated[Session, Depends(get_session)]
RECENT = 20


def now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class DisputeRow:
    at: datetime
    email: str
    pmid: str
    title: str
    criterion: str
    model_score: int | None  # None for pertinence, which is per user
    user_score: int | None
    comment: str


def _gate(user: User | None) -> Response | None:
    return gate(user, lambda u: u.is_admin, lambda u: HTMLResponse("Admins only.", 403))


def _disputes(session: Session) -> list[DisputeRow]:
    rows = session.execute(
        select(ScoreDispute, User.email, Paper.title, Grade)
        .join(User, User.id == ScoreDispute.user_id)
        .join(Paper, Paper.pmid == ScoreDispute.pmid)
        .join(Grade, Grade.id == ScoreDispute.grade_id)
        .order_by(ScoreDispute.created_at.desc())
        .limit(RECENT)
    )
    return [
        DisputeRow(
            d.created_at,
            email,
            d.pmid,
            title,
            d.criterion,
            getattr(g, d.criterion) if d.criterion != "pertinence" else None,
            d.user_score,
            d.comment,
        )
        for d, email, title, g in rows
    ]


@router.get("", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    sent: str = "",
) -> Response:
    if refused := _gate(user):
        return refused
    spent = month_spend(session, now().date())
    cap = Decimal(str(settings.llm_monthly_cap_usd))
    report, _ = calibration_report(session)
    runs = session.scalars(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(5))
    return TEMPLATES.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "user": user,
            "runs": list(runs),
            "spent": spent,
            "cap": cap,
            "share": round(spent / cap * 100) if cap else 0,
            "disputes": _disputes(session),
            "report": report,
            "labels": dict(criterion_labels()),
            "sent": sent,
        },
    )


@router.post("/send-test")
def send_test(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    mailer: MailerDep,
) -> Response:
    """Email the admin the weekly email they would get now (not recorded as a send)."""
    if refused := _gate(user):
        return refused
    assert user is not None
    mailer.send(preview(session, user, settings, now()))
    return RedirectResponse("/admin?sent=1", status_code=303)
