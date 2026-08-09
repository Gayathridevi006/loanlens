import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text
from .database import Base

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
    comments = Column(Text, default="")
    status = Column(String(20), default="REVIEW", index=True)
    risk_score = Column(Float, default=50)
    fraud_score = Column(Float, default=10)
    sentiment = Column(String(20), default="NEUTRAL")
    sentiment_confidence = Column(Float, default=.5)
    explanation = Column(Text, default="")
    ai_summary = Column(Text, default="")
    source_file = Column(String(255), default="")
    raw_data = Column(JSON, default=dict)
    processing_log = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="loan_officer")
