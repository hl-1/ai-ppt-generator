"""Persist travel conditions and versioned research."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "8d9e0f1a2b3c"
down_revision = "7c8d9e0f1a2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("travel_conditions", pg.JSONB()))
    op.add_column("projects", sa.Column("travel_research_id", pg.UUID(as_uuid=True)))
    op.add_column(
        "projects",
        sa.Column(
            "travel_booking_states",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("project_outlines", sa.Column("travel_research_id", pg.UUID(as_uuid=True)))
    op.create_table(
        "travel_research",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_signature", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("conditions", pg.JSONB(), nullable=False),
        sa.Column("data", pg.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "version"),
    )
    op.create_index("ix_travel_research_project_id", "travel_research", ["project_id"])


def downgrade() -> None:
    op.drop_table("travel_research")
    op.drop_column("project_outlines", "travel_research_id")
    op.drop_column("projects", "travel_booking_states")
    op.drop_column("projects", "travel_research_id")
    op.drop_column("projects", "travel_conditions")
