"""Add background processing jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0006_processing_jobs"
down_revision = "0005_governance"


def upgrade():
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("status", sa.String(30)),
        sa.Column("job_type", sa.String(80)),
        sa.Column("input_manifest", sa.Text()),
        sa.Column("result", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_index("ix_processing_jobs_created_at", "processing_jobs", ["created_at"])


def downgrade():
    op.drop_table("processing_jobs")
