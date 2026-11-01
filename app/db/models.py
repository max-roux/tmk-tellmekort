import uuid
from datetime import date, datetime
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
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.criteria import INTRINSIC_CRITERIA


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
