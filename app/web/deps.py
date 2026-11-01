"""External clients for request handlers, as FastAPI dependencies tests can override."""

import logging
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

import anthropic
from fastapi import Depends

from app.config import Settings, get_settings
from app.email.base import Mailer
from app.email.outbox import OutboxMailer
from app.email.postmark import PostmarkMailer
from app.embeddings.base import Embedder
from app.embeddings.voyage import VoyageEmbedder
from app.profiles.topics import TopicProposer
from app.sources.pubmed import PubMedClient

log = logging.getLogger(__name__)

SettingsDep = Annotated[Settings, Depends(get_settings)]


@lru_cache
def _postmark(server_token: str, sender: str) -> PostmarkMailer:
    # One long-lived client: it must outlive the request, since sign-in emails are sent
    # from a background task after the response.
    return PostmarkMailer(server_token=server_token, sender=sender)


def get_mailer(settings: SettingsDep) -> Mailer:
    """Postmark when configured; otherwise the local outbox folder (development)."""
    if not settings.postmark_server_token:
        log.warning("POSTMARK_SERVER_TOKEN not set: writing email to the local outbox")
        return OutboxMailer()
    return _postmark(settings.postmark_server_token, settings.email_from)


MailerDep = Annotated[Mailer, Depends(get_mailer)]


def get_embedder(settings: SettingsDep) -> Iterator[Embedder | None]:
    """None without VOYAGE_API_KEY: profile saves still work and embed later."""
    if not settings.voyage_api_key:
        yield None
        return
    embedder = VoyageEmbedder(api_key=settings.voyage_api_key, model=settings.embedding_model)
    try:
        yield embedder
    finally:
        embedder.close()


def get_pubmed(settings: SettingsDep) -> Iterator[PubMedClient]:
    with PubMedClient(
        api_key=settings.ncbi_api_key, email=settings.ncbi_email, tool=settings.ncbi_tool
    ) as client:
        yield client


def get_topic_proposer(settings: SettingsDep) -> TopicProposer | None:
    """None without ANTHROPIC_API_KEY: the surgeon types topics by hand instead."""
    if not settings.anthropic_api_key:
        return None
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return TopicProposer(client, model=settings.anthropic_model)


EmbedderDep = Annotated[Embedder | None, Depends(get_embedder)]
PubMedDep = Annotated[PubMedClient, Depends(get_pubmed)]
ProposerDep = Annotated[TopicProposer | None, Depends(get_topic_proposer)]
