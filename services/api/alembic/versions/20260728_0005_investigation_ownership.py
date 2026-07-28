"""Scope investigations and idempotency keys to their creating actor."""

import sqlalchemy as sa
from alembic import op

revision = "20260728_0005"
down_revision = "20260727_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("owner_actor", sa.String(64), nullable=True),
    )
    op.execute(
        """
        UPDATE investigations
        SET owner_actor = (
            SELECT audit_events.actor
            FROM audit_events
            WHERE audit_events.resource_id = investigations.id
              AND audit_events.action = 'investigation.created'
            ORDER BY audit_events.id
            LIMIT 1
        )
        """
    )
    op.drop_index(
        "ix_investigations_idempotency_key",
        table_name="investigations",
    )
    op.create_index(
        "ix_investigations_owner_actor",
        "investigations",
        ["owner_actor"],
    )
    op.create_index(
        "uq_investigations_owner_idempotency_key",
        "investigations",
        ["owner_actor", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_investigations_owner_idempotency_key",
        table_name="investigations",
    )
    op.drop_index(
        "ix_investigations_owner_actor",
        table_name="investigations",
    )
    op.create_index(
        "ix_investigations_idempotency_key",
        "investigations",
        ["idempotency_key"],
        unique=True,
    )
    op.drop_column("investigations", "owner_actor")
