"""Bind idempotency keys to the full investigation request."""

import sqlalchemy as sa
from alembic import op

revision = "20260727_0002"
down_revision = "20260720_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("investigations", "request_fingerprint")
