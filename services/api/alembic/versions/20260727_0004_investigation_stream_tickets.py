"""Add short-lived investigation stream tickets."""

import sqlalchemy as sa
from alembic import op

revision = "20260727_0004"
down_revision = "20260727_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_stream_tickets",
        sa.Column("ticket_hash", sa.String(64), primary_key=True),
        sa.Column(
            "investigation_id",
            sa.String(36),
            sa.ForeignKey("investigations.id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_investigation_stream_tickets_investigation_id",
        "investigation_stream_tickets",
        ["investigation_id"],
    )
    op.create_index(
        "ix_investigation_stream_tickets_expires_at",
        "investigation_stream_tickets",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_investigation_stream_tickets_expires_at",
        table_name="investigation_stream_tickets",
    )
    op.drop_index(
        "ix_investigation_stream_tickets_investigation_id",
        table_name="investigation_stream_tickets",
    )
    op.drop_table("investigation_stream_tickets")
