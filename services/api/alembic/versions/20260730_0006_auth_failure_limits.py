"""Add durable authentication failure rate limits."""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0006"
down_revision = "20260728_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_failure_limits",
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "subject_hash",
            "bucket_start",
            name="pk_auth_failure_limits",
        ),
    )
    op.create_index(
        "ix_auth_failure_limits_bucket_start",
        "auth_failure_limits",
        ["bucket_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_failure_limits_bucket_start",
        table_name="auth_failure_limits",
    )
    op.drop_table("auth_failure_limits")
