from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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
