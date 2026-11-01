"""Onboarding (SPEC.md §11): interests -> topics -> seed papers -> weights and minimums."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db.models import CriterionSettings, User
from app.db.session import get_session
from app.domain.criteria import ALL_CRITERIA
from app.domain.preferences import PreferencesError, parse_preferences
from app.domain.seeds import parse_seed_refs
from app.grading.cost import record_spend
from app.grading.rubric import criterion_guides
from app.profiles import service
from app.profiles.topics import MAX_TOPICS, ProposedTopic, TopicProposalError
from app.sources.pubmed import PubMedError
from app.web.deps import EmbedderDep, ProposerDep, PubMedDep, SettingsDep
from app.web.sessions import RequiredUser
from app.web.templating import TEMPLATES

log = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding")

SessionDep = Annotated[Session, Depends(get_session)]
BLANK_ROWS = 3
PERTINENCE_HELP = "How closely the paper matches your topics, seed papers and feedback."


def _criteria() -> list[tuple[str, str, str]]:
    """(key, name, one-line description) for the 5 criteria, pertinence first."""
    guides = [(g.key, g.name, g.description) for g in criterion_guides()]
    return [("pertinence", "Pertinence", PERTINENCE_HELP), *guides]


def _topics_page(
    request: Request,
    user: User,
    topics: list[ProposedTopic],
    *,
    error: str | None = None,
    notice: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    rows = [*topics, *[ProposedTopic("", "")] * BLANK_ROWS][: max(len(topics), MAX_TOPICS)]
    return TEMPLATES.TemplateResponse(
        request,
        "onboarding/topics.html",
        {"user": user, "step": 2, "rows": rows, "error": error, "notice": notice},
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def interests_page(
    request: Request, user: RequiredUser, session: SessionDep, proposer: ProposerDep
) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "onboarding/interests.html",
        {
            "user": user,
            "step": 1,
            "has_topics": bool(service.active_topics(session, user.id)),
            "can_propose": proposer is not None,
        },
    )


@router.post("/interests", response_class=HTMLResponse)
def propose(
    request: Request,
    user: RequiredUser,
    session: SessionDep,
    proposer: ProposerDep,
    interests: Annotated[str, Form()] = "",
) -> Response:
    if not interests.strip():
        return RedirectResponse("/onboarding/topics", status_code=303)
    if proposer is None:
        return _topics_page(
            request, user, [], notice="Topic suggestions are not set up. Type your topics below."
        )
    try:
        proposal = proposer.propose(interests)
    except TopicProposalError as e:
        log.warning("topic proposal for user %s failed: %s", user.id, e)
        return _topics_page(
            request, user, [], notice="Suggestions failed this time. Type your topics below."
        )
    record_spend(session, datetime.now(UTC).date(), proposal.cost)
    session.commit()
    return _topics_page(
        request,
        user,
        proposal.topics,
        notice="Here are suggested topics. Edit, untick or add any, then save.",
    )


@router.get("/topics", response_class=HTMLResponse)
def topics_page(request: Request, user: RequiredUser, session: SessionDep) -> HTMLResponse:
    topics = service.active_topics(session, user.id)
    return _topics_page(request, user, [ProposedTopic(t.label, t.description) for t in topics])


@router.post("/topics", response_class=HTMLResponse)
async def save_topics(
    request: Request,
    user: RequiredUser,
    session: SessionDep,
    settings: SettingsDep,
    embedder: EmbedderDep,
) -> Response:
    form = await request.form()

    def field(name: str) -> str:
        value = form.get(name)
        return " ".join(value.split()) if isinstance(value, str) else ""

    raw_count = field("count")
    count = min(int(raw_count) if raw_count.isdigit() else 0, MAX_TOPICS + BLANK_ROWS)
    submitted = [
        ProposedTopic(field(f"label_{i}"), field(f"description_{i}")) for i in range(count)
    ]
    keep = [
        ProposedTopic(t.label, t.description or t.label)
        for i, t in enumerate(submitted)
        if t.label and form.get(f"keep_{i}") is not None
    ]
    if not keep:
        return _topics_page(
            request, user, submitted, error="Keep at least one topic.", status_code=422
        )
    if len(keep) > MAX_TOPICS:
        return _topics_page(
            request, user, submitted, error=f"Keep at most {MAX_TOPICS} topics.", status_code=422
        )
    service.replace_topics(session, user.id, keep, source="onboarding")
    service.sync_embeddings(session, embedder, user.id, service.coefficients(settings))
    return RedirectResponse("/onboarding/seeds", status_code=303)


@router.get("/seeds", response_class=HTMLResponse)
def seeds_page(request: Request, user: RequiredUser, session: SessionDep) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "onboarding/seeds.html",
        {"user": user, "step": 3, "seeds": service.seed_papers(session, user.id)},
    )


@router.post("/seeds", response_class=HTMLResponse)
def add_seeds(
    request: Request,
    user: RequiredUser,
    session: SessionDep,
    settings: SettingsDep,
    embedder: EmbedderDep,
    pubmed: PubMedDep,
    refs: Annotated[str, Form()] = "",
) -> Response:
    parsed = parse_seed_refs(refs)
    context: dict[str, object] = {"user": user, "step": 3, "refs": refs}
    if not parsed.pmids and not parsed.dois:
        if parsed.unrecognised:
            context["error"] = "Those don't look like PMIDs or DOIs."
            context["seeds"] = service.seed_papers(session, user.id)
            return TEMPLATES.TemplateResponse(
                request, "onboarding/seeds.html", context, status_code=422
            )
        return RedirectResponse("/onboarding/weights", status_code=303)
    try:
        result = service.add_seeds(session, user.id, parsed, pubmed)
    except PubMedError as e:
        log.warning("seed lookup failed: %s", e)
        context["error"] = "PubMed did not answer. Try again in a minute."
        context["seeds"] = service.seed_papers(session, user.id)
        return TEMPLATES.TemplateResponse(
            request, "onboarding/seeds.html", context, status_code=502
        )
    if result.added:
        service.sync_embeddings(session, embedder, user.id, service.coefficients(settings))
    context |= {
        "result": result,
        "unrecognised": parsed.unrecognised,
        "seeds": service.seed_papers(session, user.id),
        "refs": "",
    }
    return TEMPLATES.TemplateResponse(request, "onboarding/seeds.html", context)


@router.post("/seeds/remove")
def remove_seed(
    user: RequiredUser,
    session: SessionDep,
    settings: SettingsDep,
    embedder: EmbedderDep,
    pmid: Annotated[str, Form()] = "",
) -> Response:
    service.remove_seed(session, user.id, pmid)
    service.sync_embeddings(session, embedder, user.id, service.coefficients(settings))
    return RedirectResponse("/onboarding/seeds", status_code=303)


def _weights_page(
    request: Request,
    user: User,
    values: dict[str, object],
    error: str | None = None,
) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "onboarding/weights.html",
        {"user": user, "step": 4, "criteria": _criteria(), "values": values, "error": error},
        status_code=422 if error else 200,
    )


@router.get("/weights", response_class=HTMLResponse)
def weights_page(request: Request, user: RequiredUser, session: SessionDep) -> HTMLResponse:
    current = session.get(CriterionSettings, user.id)
    values: dict[str, object] = {"hide_case_reports": True}
    for c in ALL_CRITERIA:
        values[f"w_{c}"] = getattr(current, f"w_{c}") if current else 1.0
        values[f"min_{c}"] = getattr(current, f"min_{c}") if current else None
    if current:
        values["hide_case_reports"] = current.hide_case_reports
    return _weights_page(request, user, values)


@router.post("/weights", response_class=HTMLResponse)
async def save_weights(
    request: Request,
    user: RequiredUser,
    session: SessionDep,
    settings: SettingsDep,
    embedder: EmbedderDep,
) -> Response:
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    try:
        prefs = parse_preferences(form)
    except PreferencesError as e:
        values: dict[str, object] = {**form, "hide_case_reports": "hide_case_reports" in form}
        return _weights_page(request, user, values, str(e))
    service.save_preferences(session, user.id, prefs)
    service.sync_embeddings(session, embedder, user.id, service.coefficients(settings))
    return RedirectResponse("/", status_code=303)
