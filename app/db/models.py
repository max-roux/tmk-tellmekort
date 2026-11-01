import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.criteria import ALL_CRITERIA, INTRINSIC_CRITERIA


class Paper(Base):
    """A PubMed record, keyed by PMID (SPEC.md §5)."""

    __tablename__ = "papers"

    pmid: Mapped[str] = mapped_column(Text, primary_key=True)
    doi: Mapped[str | None] = mapped_column(Text)
    pmcid: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str] = mapped_column(Text)
    journal: Mapped[str] = mapped_column(Text)
    pub_types: Mapped[list[str]] = mapped_column(ARRAY(Text))
    mesh_terms: Mapped[list[str]] = mapped_column(ARRAY(Text))
    authors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    entrez_date: Mapped[date] = mapped_column(Date, index=True)
    pub_date: Mapped[date | None] = mapped_column(Date)
    # Set when full text is checked against the PMC OA subset (milestone 5), not at fetch time.
    is_open_access: Mapped[bool] = mapped_column(Boolean, server_default="false")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Grade(Base):
    """The 4 intrinsic scores for one paper under one rubric version + model (SPEC.md §5)."""

    __tablename__ = "grades"
    __table_args__ = (
        UniqueConstraint("pmid", "rubric_version", "model"),
        CheckConstraint("input_source IN ('full_text', 'abstract')", name="input_source"),
        *(CheckConstraint(f"{c} BETWEEN 1 AND 5", name=f"{c}_range") for c in INTRINSIC_CRITERIA),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    pmid: Mapped[str] = mapped_column(ForeignKey("papers.pmid", ondelete="CASCADE"), index=True)
    rubric_version: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(Text)
    input_source: Mapped[str] = mapped_column(Text)
    proof_strength: Mapped[int] = mapped_column(SmallInteger)
    novelty: Mapped[int] = mapped_column(SmallInteger)
    depth: Mapped[int] = mapped_column(SmallInteger)
    practical_usefulness: Mapped[int] = mapped_column(SmallInteger)
    justifications: Mapped[dict[str, str]] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    study_design: Mapped[str] = mapped_column(Text)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    # Total prompt tokens, cached or not.
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmSpend(Base):
    __tablename__ = "llm_spend"

    month: Mapped[date] = mapped_column(Date, primary_key=True)
    usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default="0")


class GradingBatch(Base):
    """A submitted Message Batch, so a re-run resumes it instead of paying twice."""

    __tablename__ = "grading_batches"
    __table_args__ = (
        CheckConstraint("status IN ('submitted', 'collected', 'failed')", name="status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    rubric_version: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(Text)
    pmids: Mapped[list[str]] = mapped_column(ARRAY(Text))
    input_sources: Mapped[dict[str, str]] = mapped_column(JSONB)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="submitted")


class CalibrationItem(Base):
    """One paper in the calibration set under one rubric version (SPEC.md §12).

    surgeon_scores: {criterion: 1-5, "comment": str}, entered blind; carried forward when
    the rubric version changes. model_scores: {criterion: 1-5} from the grade for that version.
    """

    __tablename__ = "calibration_items"
    __table_args__ = (UniqueConstraint("pmid", "rubric_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    pmid: Mapped[str] = mapped_column(ForeignKey("papers.pmid", ondelete="CASCADE"))
    rubric_version: Mapped[int] = mapped_column(Integer)
    surgeon_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model_scores: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


EMBEDDING_DIM = 1024


class PaperEmbedding(Base):
    """Embedding of title + abstract. Re-embedded when the model changes."""

    __tablename__ = "paper_embeddings"

    pmid: Mapped[str] = mapped_column(
        ForeignKey("papers.pmid", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(Text)
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Candidate(Base):
    """A paper considered for grading in one ingest week (SPEC.md §6.3)."""

    __tablename__ = "candidates"

    pmid: Mapped[str] = mapped_column(
        ForeignKey("papers.pmid", ondelete="CASCADE"), primary_key=True
    )
    week_of: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    narrow_score: Mapped[float] = mapped_column(Float)
    selected_for_grading: Mapped[bool] = mapped_column(Boolean)


class User(Base):
    """A surgeon. No self-serve sign-up: accounts are added with `cli.py users add`."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("send_weekday BETWEEN 0 AND 6", name="send_weekday"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)  # stored lower-cased
    name: Mapped[str] = mapped_column(Text, server_default="")
    timezone: Mapped[str] = mapped_column(Text, server_default="Europe/Copenhagen")
    send_weekday: Mapped[int] = mapped_column(SmallInteger, server_default="0")  # Monday
    send_local_time: Mapped[time] = mapped_column(Time, server_default="06:30")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # May blind-grade the calibration set (SPEC.md §12); admins always can.
    can_calibrate: Mapped[bool] = mapped_column(Boolean, server_default="false")


class MagicLink(Base):
    """A sign-in link. Only the SHA-256 of the token is stored (SPEC.md §16)."""

    __tablename__ = "magic_links"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    """One /login request, for rate limiting per email and overall."""

    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Topic(Base):
    """A topic chip. `description` (PubMed vocabulary) is what gets embedded."""

    __tablename__ = "topics"
    __table_args__ = (CheckConstraint("source IN ('onboarding', 'manual')", name="source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SeedPaper(Base):
    __tablename__ = "seed_papers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    pmid: Mapped[str] = mapped_column(
        ForeignKey("papers.pmid", ondelete="CASCADE"), primary_key=True
    )


class CriterionSettings(Base):
    """Per-user weights (0-5), minimums (1-5 or none) and hard filters (SPEC.md §5, §8)."""

    __tablename__ = "criterion_settings"
    __table_args__ = (
        *(CheckConstraint(f"w_{c} BETWEEN 0 AND 5", name=f"w_{c}_range") for c in ALL_CRITERIA),
        *(CheckConstraint(f"min_{c} BETWEEN 1 AND 5", name=f"min_{c}_range") for c in ALL_CRITERIA),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    w_pertinence: Mapped[float] = mapped_column(Float, server_default="1")
    w_proof_strength: Mapped[float] = mapped_column(Float, server_default="1")
    w_novelty: Mapped[float] = mapped_column(Float, server_default="1")
    w_depth: Mapped[float] = mapped_column(Float, server_default="1")
    w_practical_usefulness: Mapped[float] = mapped_column(Float, server_default="1")
    min_pertinence: Mapped[int | None] = mapped_column(SmallInteger)
    min_proof_strength: Mapped[int | None] = mapped_column(SmallInteger)
    min_novelty: Mapped[int | None] = mapped_column(SmallInteger)
    min_depth: Mapped[int | None] = mapped_column(SmallInteger)
    min_practical_usefulness: Mapped[int | None] = mapped_column(SmallInteger)
    hide_case_reports: Mapped[bool] = mapped_column(Boolean, server_default="true")
    study_types: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


class ProfileVector(Base):
    """Cached profile vector (SPEC.md §8.1); recomputed on any topic, seed or feedback change."""

    __tablename__ = "profile_vectors"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(Text)
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


FEEDBACK_KINDS = ("read", "unread", "like", "unlike", "not_for_me", "undismiss")


class Feedback(Base):
    """Append-only feedback events; a paper's state per user is derived from them (§9)."""

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in FEEDBACK_KINDS) + ")", name="kind"
        ),
        CheckConstraint("source IN ('email', 'app')", name="source"),
        Index(
            "uq_feedback_send_pmid_kind",
            "send_id",
            "pmid",
            "kind",
            unique=True,
            postgresql_where=text("send_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pmid: Mapped[str] = mapped_column(ForeignKey("papers.pmid", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    # The weekly email an email action came from; one event per (send, paper, kind).
    send_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("email_sends.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScoreDispute(Base):
    """A surgeon disagreeing with one score; never changes the shared grade (§9)."""

    __tablename__ = "score_disputes"
    __table_args__ = (
        CheckConstraint(
            "criterion IN (" + ", ".join(f"'{c}'" for c in ALL_CRITERIA) + ")", name="criterion"
        ),
        CheckConstraint("user_score BETWEEN 1 AND 5", name="user_score_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pmid: Mapped[str] = mapped_column(ForeignKey("papers.pmid", ondelete="CASCADE"))
    grade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grades.id", ondelete="CASCADE"))
    criterion: Mapped[str] = mapped_column(Text)
    user_score: Mapped[int | None] = mapped_column(SmallInteger)
    comment: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailSend(Base):
    """One weekly email (SPEC.md §10). Unique per user and local week, so it is sent once.

    No papers (both picks null) means a "quiet week" email.
    """

    __tablename__ = "email_sends"
    __table_args__ = (UniqueConstraint("user_id", "week_of"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    week_of: Mapped[date] = mapped_column(Date)  # Monday of the week, in the user's timezone
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    postmark_message_id: Mapped[str | None] = mapped_column(Text)
    fresh_pmid: Mapped[str | None] = mapped_column(ForeignKey("papers.pmid", ondelete="SET NULL"))
    missed_pmid: Mapped[str | None] = mapped_column(ForeignKey("papers.pmid", ondelete="SET NULL"))
