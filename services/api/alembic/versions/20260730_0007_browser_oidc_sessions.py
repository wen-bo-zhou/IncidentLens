"""Add browser OIDC login transactions and sessions."""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0007"
down_revision = "20260730_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auth_failure_limits",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                "UPDATE auth_failure_limits "
                "SET expires_at = bucket_start + INTERVAL '1 day' "
                "WHERE expires_at IS NULL"
            )
        )
    elif dialect == "sqlite":
        op.execute(
            sa.text(
                "UPDATE auth_failure_limits "
                "SET expires_at = datetime(bucket_start, '+1 day') "
                "WHERE expires_at IS NULL"
            )
        )
    else:
        raise RuntimeError(f"Unsupported migration dialect: {dialect}")
    with op.batch_alter_table("auth_failure_limits") as batch_op:
        batch_op.alter_column(
            "expires_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
    op.create_index(
        "ix_auth_failure_limits_expires_at",
        "auth_failure_limits",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "oidc_login_transactions",
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("client_hash", sa.String(64), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("return_to", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "state_hash",
            name="pk_oidc_login_transactions",
        ),
    )
    op.create_index(
        "ix_oidc_login_transactions_browser_hash",
        "oidc_login_transactions",
        ["browser_hash"],
        unique=False,
    )
    op.create_index(
        "ix_oidc_login_transactions_client_hash",
        "oidc_login_transactions",
        ["client_hash"],
        unique=False,
    )
    op.create_index(
        "ix_oidc_login_transactions_expires_at",
        "oidc_login_transactions",
        ["expires_at"],
        unique=False,
    )
    admission_table = op.create_table(
        "admission_control",
        sa.Column("lock_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("lock_id", name="pk_admission_control"),
    )
    op.bulk_insert(admission_table, [{"lock_id": 1}])
    op.create_table(
        "browser_sessions",
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_hash", name="pk_browser_sessions"),
    )
    op.create_index(
        "ix_browser_sessions_expires_at",
        "browser_sessions",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_browser_sessions_expires_at",
        table_name="browser_sessions",
    )
    op.drop_table("browser_sessions")
    op.drop_table("admission_control")
    op.drop_index(
        "ix_oidc_login_transactions_expires_at",
        table_name="oidc_login_transactions",
    )
    op.drop_index(
        "ix_oidc_login_transactions_client_hash",
        table_name="oidc_login_transactions",
    )
    op.drop_index(
        "ix_oidc_login_transactions_browser_hash",
        table_name="oidc_login_transactions",
    )
    op.drop_table("oidc_login_transactions")
    op.drop_index(
        "ix_auth_failure_limits_expires_at",
        table_name="auth_failure_limits",
    )
    with op.batch_alter_table("auth_failure_limits") as batch_op:
        batch_op.drop_column("expires_at")
