import re
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.users import add_user
from app.config import Settings
from app.db.models import CriterionSettings, EmailSend, User
from app.email.base import EmailMessage, MailerError
from app.feed import feedback
from app.jobs.send_due_emails import preview, send_due
from app.profiles import service
from app.profiles.topics import ProposedTopic
from tests.fakes import FakeEmbedder
from tests.feed_setup import EVEN, PINNED, TOPIC, grade, user

pytestmark = pytest.mark.db
__all__ = ["user"]  # pytest fixture

SETTINGS = Settings(  # type: ignore[call-arg]
    _env_file=None, base_url="https://tmk.test", admin_email="admin@example.com"
)
SUNDAY = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)  # Monday 06:30 slot of this week has passed
MONDAY_AT_SLOT = datetime(2026, 11, 2, 5, 35, tzinfo=UTC)  # 06:35 Copenhagen
MONDAY_EARLY = datetime(2026, 11, 2, 5, 0, tzinfo=UTC)  # 06:00 Copenhagen, before the slot
# Fixture papers: 42963307 / 42963182 entered 2026-10-30 (fresh), 42949936 on 10-28 (fresh).


class Mailer:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = fail

    def send(self, message: EmailMessage) -> str:
        if self.fail:
            raise MailerError("postmark: error 300: Invalid email request")
        self.sent.append(message)
        return f"pm-{len(self.sent)}"


def to_user(mailer: Mailer, user: User) -> list[EmailMessage]:
    return [m for m in mailer.sent if m.to == user.email]


def test_due_user_gets_fresh_and_missed_once_per_week(db_session: Session, user: User) -> None:
    grade(db_session, "42963307", 5)
    grade(db_session, "42949936", 4)
    mailer = Mailer()
    stats = send_due(db_session, SETTINGS, mailer, SUNDAY)
    assert (stats.sent, stats.quiet, stats.failed) == (1, 0, 0)
    (msg,) = to_user(mailer, user)
    assert msg.subject.startswith("Tell Me Kort: ")
    assert "Fresh this week" in msg.text and "You may have missed" in msg.text
    assert msg.text.index("Fresh this week") < msg.text.index("You may have missed")
    links = re.findall(r"https://tmk\.test/a/\w+#[\w.-]+", msg.html)
    assert len(links) == 6  # like, read, not for me for each of 2 papers
    assert "https://tmk.test/paper/42963307" in msg.html
    row = db_session.scalars(select(EmailSend)).one()
    assert (row.fresh_pmid, row.missed_pmid) == ("42963307", "42949936")
    assert row.postmark_message_id == "pm-1"

    assert send_due(db_session, SETTINGS, mailer, SUNDAY).sent == 0  # already sent this week


def test_not_due_before_the_slot_or_before_onboarding(db_session: Session, user: User) -> None:
    grade(db_session, "42963307", 5)
    add_user(db_session, "new@example.com")  # no criterion settings yet: not onboarded
    mailer = Mailer()
    assert send_due(db_session, SETTINGS, mailer, MONDAY_EARLY).sent == 0
    assert mailer.sent == []


def test_papers_already_sent_are_not_sent_again(db_session: Session, user: User) -> None:
    grade(db_session, "42963307", 5)
    grade(db_session, "42949936", 4)
    send_due(db_session, SETTINGS, Mailer(), SUNDAY)
    grade(db_session, "42963182", 4)
    next_week = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    send_due(db_session, SETTINGS, Mailer(), next_week)
    rows = db_session.scalars(select(EmailSend).order_by(EmailSend.week_of)).all()
    # 42963182 entered 10-30, more than 7 days before Nov 8: it can only be a missed pick.
    assert (rows[1].fresh_pmid, rows[1].missed_pmid) == (None, "42963182")


def test_quiet_week_tells_the_user_and_alerts_the_admin(db_session: Session, user: User) -> None:
    mailer = Mailer()
    stats = send_due(db_session, SETTINGS, mailer, SUNDAY)
    assert (stats.sent, stats.quiet) == (1, 1)
    (msg,) = to_user(mailer, user)
    assert "quiet week" in msg.text.lower() and "https://tmk.test/" in msg.text
    assert msg.subject == "Tell Me Kort: a quiet week"
    (alert,) = [m for m in mailer.sent if m.to == "admin@example.com"]
    assert alert.subject.startswith("[TMK] ")
    assert user.email in alert.text


def test_failed_send_is_retried_on_the_next_run(db_session: Session, user: User) -> None:
    grade(db_session, "42963307", 5)
    stats = send_due(db_session, SETTINGS, Mailer(fail=True), SUNDAY)
    assert (stats.sent, stats.failed) == (0, 1)
    assert db_session.scalars(select(EmailSend)).all() == []
    assert send_due(db_session, SETTINGS, Mailer(), SUNDAY).sent == 1


def test_inline_reasons_follow_the_users_top_two_weights(db_session: Session, user: User) -> None:
    grade(db_session, "42963307", 5)
    cs = db_session.get(CriterionSettings, user.id)
    assert cs is not None
    cs.w_novelty, cs.w_depth = 5.0, 4.0
    db_session.commit()
    mailer = Mailer()
    send_due(db_session, SETTINGS, mailer, SUNDAY)
    (msg,) = to_user(mailer, user)
    assert "novelty because" in msg.text and "depth because" in msg.text
    assert "proof_strength because" not in msg.text


def test_one_users_bug_does_not_stop_the_others_and_alerts_the_admin(
    db_session: Session, user: User
) -> None:
    other = add_user(db_session, "second@example.com")
    e = FakeEmbedder(pinned=PINNED)
    service.replace_topics(db_session, other.id, [ProposedTopic("Fibula", TOPIC)], "onboarding")
    service.save_preferences(db_session, other.id, EVEN)
    assert service.sync_embeddings(db_session, e, other.id, service.coefficients(SETTINGS))

    class BrokenForOne(Mailer):
        def send(self, message: EmailMessage) -> str:
            if message.to == user.email:
                raise RuntimeError("template bug")
            return super().send(message)

    grade(db_session, "42963307", 5)
    mailer = BrokenForOne()
    stats = send_due(db_session, SETTINGS, mailer, MONDAY_AT_SLOT)
    assert (stats.sent, stats.failed) == (1, 1)
    assert len(to_user(mailer, other)) == 1
    (alert,) = [m for m in mailer.sent if m.to == "admin@example.com"]
    assert "RuntimeError" in alert.text and user.email not in alert.subject
    claims = db_session.scalars(select(EmailSend.user_id)).all()
    assert claims == [other.id]  # the failed user's claim is released for the next run

    # The next hourly retry fails the same way, but doesn't alert again.
    retry = BrokenForOne()
    assert send_due(db_session, SETTINGS, retry, MONDAY_AT_SLOT + timedelta(hours=1)).failed == 1
    assert [m for m in retry.sent if m.to == "admin@example.com"] == []


def test_a_late_sunday_slot_sends_after_the_week_rolls_over(
    db_session: Session, user: User
) -> None:
    user.send_weekday, user.send_local_time = 6, time(23, 30)
    db_session.commit()
    grade(db_session, "42963307", 5)
    monday_0005_local = datetime(2026, 11, 1, 23, 5, tzinfo=UTC)
    assert send_due(db_session, SETTINGS, Mailer(), monday_0005_local).sent == 1
    (send,) = db_session.scalars(select(EmailSend)).all()
    assert send.week_of == date(2026, 10, 26)  # counted as last week's email


def test_preview_renders_without_recording(db_session: Session, user: User) -> None:
    grade(db_session, "42963307", 5)
    message = preview(db_session, user, SETTINGS, SUNDAY)
    assert "Fresh this week" in message.text
    assert db_session.scalars(select(EmailSend)).all() == []


def test_a_paper_the_user_already_liked_is_not_emailed(db_session: Session, user: User) -> None:
    grade(db_session, "42963307", 5)
    grade(db_session, "42949936", 4)
    feedback.record(db_session, user.id, "42963307", "like", "app", SETTINGS)
    send_due(db_session, SETTINGS, Mailer(), SUNDAY)
    row = db_session.scalars(select(EmailSend)).one()
    assert "42963307" not in (row.fresh_pmid, row.missed_pmid)
    assert row.fresh_pmid == "42949936"
