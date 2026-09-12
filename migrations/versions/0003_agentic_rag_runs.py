"""Persist encrypted live agentic RAG runs."""
from alembic import op
import sqlalchemy as sa

revision = "0003_agentic_rag_runs"
down_revision = "0002_encrypt_payload_storage"


def upgrade():
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("application_id", sa.String(), nullable=False),
        sa.Column("query", sa.Text()),
        sa.Column("intent", sa.String(40)),
        sa.Column("status", sa.String(30)),
        sa.Column("answer", sa.Text()),
        sa.Column("decision", sa.Text()),
        sa.Column("fraud_assessment", sa.Text()),
        sa.Column("evidence", sa.Text()),
        sa.Column("policy_evidence", sa.Text()),
        sa.Column("document_assessment", sa.Text()),
        sa.Column("verification", sa.Text()),
        sa.Column("trace", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_agent_runs_application_id", "agent_runs", ["application_id"])
    op.create_index("ix_agent_runs_intent", "agent_runs", ["intent"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])


def downgrade():
    op.drop_table("agent_runs")
