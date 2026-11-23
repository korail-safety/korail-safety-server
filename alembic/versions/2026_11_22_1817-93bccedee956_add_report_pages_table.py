"""add report_pages table

Revision ID: 93bccedee956
Revises: 4c31543241c6
Create Date: 2026-11-22 18:17:28.024669+09:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "93bccedee956"
down_revision: str | Sequence[str] | None = "4c31543241c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "report_pages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("image_key", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["reports.id"],
            name=op.f("fk_report_pages_report_id_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_pages")),
        sa.UniqueConstraint("report_id", "page_no", name=op.f("uq_report_pages_report_id_page_no")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("report_pages")
