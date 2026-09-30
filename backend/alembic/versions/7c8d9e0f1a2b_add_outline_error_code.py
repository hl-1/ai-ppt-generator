"""add outline error code

Revision ID: 7c8d9e0f1a2b
Revises: f6a7b8c9d0e1
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c8d9e0f1a2b"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "project_outlines",
        sa.Column("error_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_outlines", "error_code")
