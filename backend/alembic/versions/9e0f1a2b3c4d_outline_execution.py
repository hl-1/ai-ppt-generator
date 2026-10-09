"""Persist outline execution stages and public failure details."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "9e0f1a2b3c4d"
down_revision = "8d9e0f1a2b3c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_outlines", sa.Column("execution", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("project_outlines", "execution")
