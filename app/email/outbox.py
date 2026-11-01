"""Development mailer: writes messages to a local folder instead of sending them.

Used when POSTMARK_SERVER_TOKEN is unset. The folder (var/outbox by default) is
gitignored; messages may contain sign-in links, so it is for local use only.
"""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.email.base import EmailMessage

DEFAULT_DIR = Path(__file__).parents[2] / "var" / "outbox"


class OutboxMailer:
    def __init__(self, directory: Path = DEFAULT_DIR) -> None:
        self.directory = directory

    def send(self, message: EmailMessage) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        message_id = f"outbox-{uuid.uuid4()}"
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", message.subject.lower()).strip("-")[:40]
        stem = self.directory / f"{stamp}-{slug}-{message_id[-8:]}"
        header = f"To: {message.to}\nSubject: {message.subject}\nId: {message_id}\n\n"
        stem.with_suffix(".txt").write_text(header + message.text)
        stem.with_suffix(".html").write_text(message.html)
        return message_id
