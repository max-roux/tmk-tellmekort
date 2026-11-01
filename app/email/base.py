"""Outgoing email interface, so Postmark can be swapped or faked (SPEC.md §3, §10.5)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
    keep_trailing_newline=True,
)


NAME = "Tell Me Kort"


def sender_with_name(address: str) -> str:
    """`Tell Me Kort <address>`, unless EMAIL_FROM already carries a display name."""
    return address if "<" in address else f"{NAME} <{address}>"


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    def send(self, message: EmailMessage) -> str:
        """Send one message; returns the provider's message id."""
        ...


class MailerError(Exception):
    pass


def render(template: str, subject: str, to: str, **context: object) -> EmailMessage:
    """Render `<template>.txt` and `<template>.html` into one message."""
    return EmailMessage(
        to=to,
        subject=subject,
        text=TEMPLATES.get_template(f"{template}.txt").render(**context),
        html=TEMPLATES.get_template(f"{template}.html").render(**context),
    )
