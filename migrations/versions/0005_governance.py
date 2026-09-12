"""Add decision overrides and persistent audit events."""
from alembic import op
import sqlalchemy as sa

revision = "0005_governance"
down_revision = "0004_pgvector_evidence"


def upgrade():
    op.create_table(
        "decision_overrides",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("application_id", sa.String(), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=False),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_decision_overrides_application_id", "decision_overrides", ["application_id"])
    op.create_index("ix_decision_overrides_created_at", "decision_overrides", ["created_at"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor", sa.String(160)),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(80)),
        sa.Column("resource_id", sa.String()),
        sa.Column("details", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_audit_events_actor", "audit_events", ["actor"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade():
    op.drop_table("audit_events")
    op.drop_table("decision_overrides")
