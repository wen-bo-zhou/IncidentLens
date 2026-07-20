"""Initial investigation, event, remediation and audit tables."""

import sqlalchemy as sa
from alembic import op
from incidentlens.retrieval import EMBEDDING_DIMENSIONS
from pgvector.sqlalchemy import Vector

revision = "20260720_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "incident_packages",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("package_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incident_packages_visibility", "incident_packages", ["visibility"])
    op.create_index(
        "ix_incident_packages_package_hash",
        "incident_packages",
        ["package_hash"],
        unique=True,
    )
    op.create_table(
        "runbook_chunks",
        sa.Column("id", sa.String(180), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(120),
            sa.ForeignKey("incident_packages.id"),
            nullable=False,
        ),
        sa.Column("service", sa.String(120), nullable=False),
        sa.Column("content", sa.String(2000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
    )
    op.create_index("ix_runbook_chunks_incident_id", "runbook_chunks", ["incident_id"])
    op.create_index("ix_runbook_chunks_service", "runbook_chunks", ["service"])
    op.create_index(
        "ix_runbook_chunks_content_hash",
        "runbook_chunks",
        ["content_hash"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_runbook_chunks_embedding_hnsw "
            "ON runbook_chunks USING hnsw (embedding vector_cosine_ops)"
        )
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(120), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_investigations_case_id", "investigations", ["case_id"])
    op.create_index("ix_investigations_status", "investigations", ["status"])
    op.create_index(
        "ix_investigations_idempotency_key",
        "investigations",
        ["idempotency_key"],
        unique=True,
    )
    op.create_table(
        "investigation_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "investigation_id",
            sa.String(36),
            sa.ForeignKey("investigations.id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "investigation_id",
            "sequence",
            name="uq_event_investigation_sequence",
        ),
    )
    op.create_index(
        "ix_investigation_events_investigation_id",
        "investigation_events",
        ["investigation_id"],
    )
    op.create_table(
        "remediations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "investigation_id",
            sa.String(36),
            sa.ForeignKey("investigations.id"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("approved_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_remediations_investigation_id", "remediations", ["investigation_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(120), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("remediations")
    op.drop_table("investigation_events")
    op.drop_table("investigations")
    op.drop_table("runbook_chunks")
    op.drop_table("incident_packages")
