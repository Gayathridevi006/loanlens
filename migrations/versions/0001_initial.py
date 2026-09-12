"""Initial LoanLens schema with encrypted raw application payloads."""
from alembic import op
import sqlalchemy as sa

revision="0001_initial"
down_revision=None

def upgrade():
    op.create_table("applications",
        sa.Column("id",sa.String(),primary_key=True),sa.Column("applicant_name",sa.String(160),nullable=False),
        sa.Column("email",sa.String(200)),sa.Column("loan_type",sa.String(80)),sa.Column("loan_amount",sa.Float()),
        sa.Column("income",sa.Float()),sa.Column("credit_score",sa.Integer()),sa.Column("dti",sa.Float()),
        sa.Column("employment_years",sa.Float()),sa.Column("existing_loans",sa.Integer()),sa.Column("comments",sa.Text()),
        sa.Column("status",sa.String(20)),sa.Column("risk_score",sa.Float()),sa.Column("fraud_score",sa.Float()),
        sa.Column("sentiment",sa.String(20)),sa.Column("sentiment_confidence",sa.Float()),sa.Column("explanation",sa.Text()),
        sa.Column("ai_summary",sa.Text()),sa.Column("source_file",sa.String(255)),sa.Column("raw_data",sa.Text()),
        sa.Column("processing_log",sa.JSON()),sa.Column("created_at",sa.DateTime()),sa.Column("updated_at",sa.DateTime()))
    op.create_index("ix_applications_applicant_name","applications",["applicant_name"])
    op.create_index("ix_applications_status","applications",["status"])
    op.create_index("ix_applications_created_at","applications",["created_at"])
    op.create_table("users",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("username",sa.String(80),nullable=False,unique=True),sa.Column("password_hash",sa.String(255),nullable=False),sa.Column("role",sa.String(30)))
    op.create_table("evaluation_runs",sa.Column("id",sa.String(),primary_key=True),sa.Column("name",sa.String(160),nullable=False),sa.Column("dataset_size",sa.Integer()),sa.Column("metrics",sa.JSON()),sa.Column("failures",sa.JSON()),sa.Column("created_at",sa.DateTime()))
    op.create_index("ix_evaluation_runs_created_at","evaluation_runs",["created_at"])

def downgrade():
    op.drop_table("evaluation_runs"); op.drop_table("users"); op.drop_table("applications")
