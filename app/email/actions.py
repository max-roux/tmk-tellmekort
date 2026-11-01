"""One-tap links in the weekly email (SPEC.md §10.4).

The link is BASE_URL/a#<token>: the token stays in the URL fragment, out of server logs,
and opening the link only renders a page that POSTs it. Tokens are signed, carry the
user, paper, action and send, and expire after 30 days. No sign-in is needed.
"""

import uuid
from dataclasses import dataclass

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import Settings

ACTIONS = ("like", "read", "not_for_me")
MAX_AGE_S = 30 * 24 * 3600
_SALT = "email-action"


@dataclass(frozen=True)
class EmailAction:
    user_id: uuid.UUID
    pmid: str
    action: str
    send_id: uuid.UUID


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def make_token(
    settings: Settings, user_id: uuid.UUID, pmid: str, action: str, send_id: uuid.UUID
) -> str:
    if action not in ACTIONS:
        raise ValueError(f"not an email action: {action!r}")
    return _serializer(settings).dumps([str(user_id), pmid, action, str(send_id)])


def action_link(
    settings: Settings, user_id: uuid.UUID, pmid: str, action: str, send_id: uuid.UUID
) -> str:
    token = make_token(settings, user_id, pmid, action, send_id)
    return f"{settings.base_url.rstrip('/')}/a#{token}"


def read_token(settings: Settings, token: str, max_age: int = MAX_AGE_S) -> EmailAction | None:
    """The action, or None when the token is forged, malformed or expired."""
    try:
        user_id, pmid, action, send_id = _serializer(settings).loads(token, max_age=max_age)
        parsed = EmailAction(uuid.UUID(user_id), pmid, action, uuid.UUID(send_id))
    except (BadSignature, ValueError, TypeError):
        return None
    return parsed if parsed.action in ACTIONS else None
