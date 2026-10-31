"""papers

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("pmid", sa.Text(), nullable=False),
        sa.Column("doi", sa.Text(), nullable=True),
        sa.Column("pmcid", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("journal", sa.Text(), nullable=False),
        sa.Column("pub_types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("mesh_terms", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("authors", postgresql.JSONB(), nullable=False),
        sa.Column("entrez_date", sa.Date(), nullable=False),
        sa.Column("pub_date", sa.Date(), nullable=True),
        sa.Column("is_open_access", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("pmid", name=op.f("pk_papers")),
    )
    op.create_index(op.f("ix_papers_entrez_date"), "papers", ["entrez_date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_papers_entrez_date"), table_name="papers")
    op.drop_table("papers")
