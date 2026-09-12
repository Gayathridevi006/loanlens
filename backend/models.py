import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text
from .database import Base
from .security import EncryptedJSON, EncryptedText

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # SQLite/test fallback; PostgreSQL deployments install pgvector.
    Vector = None

class Application(Base):
    __tablename__ = "applications"
    id = Column(String, primary_key=True, default=lambda: f"LN-{uuid.uuid4().hex[:8].upper()}")
    applicant_name = Column(String(160), nullable=False, index=True)
    email = Column(String(200), default="")
    loan_type = Column(String(80), default="Personal Loan")
    loan_amount = Column(Float, default=0)
    income = Column(Float, default=0)
    credit_score = Column(Integer, default=650)
    dti = Column(Float, default=0)
    employment_years = Column(Float, default=0)
    existing_loans = Column(Integer, default=0)
    comments = Column(EncryptedText, default="")
    status = Column(String(20), default="REVIEW", index=True)
    risk_score = Column(Float, default=50)
    fraud_score = Column(Float, default=10)
    sentiment = Column(String(20), default="NEUTRAL")
    sentiment_confidence = Column(Float, default=.5)
    explanation = Column(Text, default="")
    ai_summary = Column(Text, default="")
    source_file = Column(String(255), default="")
    raw_data = Column(EncryptedJSON, default=dict)
    processing_log = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="loan_officer")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id = Column(String, primary_key=True, default=lambda: f"EV-{uuid.uuid4().hex[:8].upper()}")
    name = Column(String(160), nullable=False, default="RAG backtest")
    dataset_size = Column(Integer, default=0)
    metrics = Column(JSON, default=dict)
    failures = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AgentRun(Base):
    """Encrypted audit record for one live agentic RAG execution."""
    __tablename__ = "agent_runs"
    id = Column(String, primary_key=True, default=lambda: f"AR-{uuid.uuid4().hex[:10].upper()}")
    application_id = Column(String, nullable=False, index=True)
    query = Column(EncryptedText, default="")
    intent = Column(String(40), default="general", index=True)
    status = Column(String(30), default="COMPLETED", index=True)
    answer = Column(EncryptedText, default="")
    decision = Column(EncryptedJSON, default=dict)
    fraud_assessment = Column(EncryptedJSON, default=dict)
    evidence = Column(EncryptedJSON, default=list)
    policy_evidence = Column(EncryptedJSON, default=list)
    document_assessment = Column(EncryptedJSON, default=dict)
    verification = Column(EncryptedJSON, default=dict)
    trace = Column(EncryptedJSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class EvidenceEmbedding(Base):
    __tablename__ = "evidence_embeddings"
    id = Column(String, primary_key=True)
    application_id = Column(String, nullable=False, index=True)
    chunk_id = Column(String, nullable=False)
    source = Column(String(255), default="")
    document_type = Column(String(80), default="unknown", index=True)
    page = Column(Integer, nullable=True)
    section = Column(String(80), default="")
    content = Column(EncryptedText, default="")
    chunk_metadata = Column(EncryptedJSON, default=dict)
    embedding = Column(Vector(384) if Vector is not None else JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DecisionOverride(Base):
    __tablename__ = "decision_overrides"
    id = Column(String, primary_key=True, default=lambda: f"OV-{uuid.uuid4().hex[:8].upper()}")
    application_id = Column(String, nullable=False, index=True)
    previous_status = Column(String(20), nullable=False)
    new_status = Column(String(20), nullable=False)
    reason = Column(EncryptedText, nullable=False)
    actor = Column(String(160), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(String, primary_key=True, default=lambda: f"AU-{uuid.uuid4().hex[:10].upper()}")
    actor = Column(String(160), default="system", index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(80), default="")
    resource_id = Column(String, default="", index=True)
    details = Column(EncryptedJSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id = Column(String, primary_key=True, default=lambda: f"JOB-{uuid.uuid4().hex[:10].upper()}")
    status = Column(String(30), default="QUEUED", index=True)
    job_type = Column(String(80), default="document_intake")
    input_manifest = Column(EncryptedJSON, default=dict)
    result = Column(EncryptedJSON, default=dict)
    error = Column(EncryptedText, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
