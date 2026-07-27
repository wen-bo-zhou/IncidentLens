"""Persist runner daily quota usage."""

import sqlalchemy as sa
from alembic import op

revision = "20260727_0003"
down_revision = "20260727_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_run_usage",
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("actor_hash", sa.String(64), nullable=False),
        sa.Column("run_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("usage_date", "actor_hash"),
    )


def downgrade() -> None:
    op.drop_table("daily_run_usage")
