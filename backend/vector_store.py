"""pgvector evidence index with a deterministic SQLite development fallback."""
from __future__ import annotations

import hashlib
import math
from typing import Any

from sqlalchemy.orm import Session

from .agentic_rag import EvidenceChunk
from .models import EvidenceEmbedding, Vector
from .rag_evaluation import tokens


EMBEDDING_DIMENSIONS = 384


def local_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Create a stable feature-hashed embedding without sending data off-host."""
    vector = [0.0] * dimensions
    terms = tokens(text)
    for position, term in enumerate(terms):
        digest = hashlib.blake2b(term.encode(), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = -1.0 if digest[4] & 1 else 1.0
        vector[bucket] += sign * (1.0 + min(len(term), 12) / 12) / math.sqrt(position + 1)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]


def sync_evidence_index(db: Session, application_id: str, chunks: list[EvidenceChunk]) -> None:
    db.query(EvidenceEmbedding).filter(EvidenceEmbedding.application_id == application_id).delete()
    for chunk in chunks:
        db.add(EvidenceEmbedding(
            id=f"{application_id}:{chunk.id}",
            application_id=application_id,
            chunk_id=chunk.id,
            source=chunk.source,
            document_type=chunk.document_type,
            page=chunk.page,
            section=chunk.section,
            content=chunk.text,
            chunk_metadata={"fields": list(chunk.fields)},
            embedding=local_embedding(chunk.text),
        ))
    db.flush()


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_norm * right_norm)


def semantic_search(
    db: Session,
    application_id: str,
    query: str,
    top_k: int = 8,
    document_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    query_vector = local_embedding(query)
    statement = db.query(EvidenceEmbedding).filter(EvidenceEmbedding.application_id == application_id)
    if document_types:
        statement = statement.filter(EvidenceEmbedding.document_type.in_(document_types))
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql" and Vector is not None:
        rows = statement.order_by(EvidenceEmbedding.embedding.cosine_distance(query_vector)).limit(top_k).all()
        return [
            {"id": row.chunk_id, "semantic_rank": rank, "source": row.source, "document_type": row.document_type}
            for rank, row in enumerate(rows, 1)
        ]
    rows = statement.all()
    ranked = sorted(
        rows,
        key=lambda row: _cosine(query_vector, list(row.embedding) if row.embedding is not None else []),
        reverse=True,
    )[:top_k]
    return [
        {"id": row.chunk_id, "semantic_rank": rank, "source": row.source, "document_type": row.document_type}
        for rank, row in enumerate(ranked, 1)
    ]


def vector_backend(db: Session) -> dict[str, Any]:
    dialect = db.get_bind().dialect.name
    return {
        "dialect": dialect,
        "engine": "pgvector" if dialect == "postgresql" and Vector is not None else "local-cosine-fallback",
        "dimensions": EMBEDDING_DIMENSIONS,
        "embedding_model": "loanlens-feature-hash-v1",
        "data_residency": "local",
    }
