"""Add pgvector-backed evidence storage."""
from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

revision = "0004_pgvector_evidence"
down_revision = "0003_agentic_rag_runs"


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    vector_type = Vector(384) if Vector is not None and connection.dialect.name == "postgresql" else sa.JSON()
    op.create_table(
        "evidence_embeddings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("application_id", sa.String(), nullable=False),
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(255)),
        sa.Column("document_type", sa.String(80)),
        sa.Column("page", sa.Integer()),
        sa.Column("section", sa.String(80)),
        sa.Column("content", sa.Text()),
        sa.Column("chunk_metadata", sa.Text()),
        sa.Column("embedding", vector_type, nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_evidence_embeddings_application_id", "evidence_embeddings", ["application_id"])
    op.create_index("ix_evidence_embeddings_document_type", "evidence_embeddings", ["document_type"])
    if connection.dialect.name == "postgresql":
        op.execute("CREATE INDEX ix_evidence_embeddings_hnsw ON evidence_embeddings USING hnsw (embedding vector_cosine_ops)")


def downgrade():
    op.drop_table("evidence_embeddings")
