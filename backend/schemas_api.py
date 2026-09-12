from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class ApplicationCreate(BaseModel):
    applicant_name: str = Field(min_length=2, max_length=160)
    email: str = ""
    loan_type: str = "Personal Loan"
    loan_amount: float = Field(default=0, ge=0)
    income: float = Field(default=0, ge=0)
    credit_score: int = Field(default=650, ge=300, le=900)
    dti: float = Field(default=0, ge=0, le=100)
    employment_years: float = Field(default=0, ge=0)
    existing_loans: int = Field(default=0, ge=0)
    comments: str = ""

class ApplicationOut(ApplicationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    risk_score: float
    fraud_score: float
    sentiment: str
    sentiment_confidence: float
    explanation: str
    ai_summary: str
    source_file: str
    processing_log: list
    created_at: datetime

class LoginRequest(BaseModel):
    username: str
    password: str


class BootstrapAdminRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    bootstrap_secret: str = Field(min_length=8, max_length=256)

class EvaluationCase(BaseModel):
    case_id: str
    query: str = Field(min_length=2)
    corpus: list[dict]
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_answer_terms: list[str] = Field(default_factory=list)
    expected_not_terms: list[str] = Field(default_factory=list)
    generated_answer: str = ""
    expected_decision: Optional[str] = None
    actual_decision: Optional[str] = None

class BacktestRequest(BaseModel):
    name: str = "RAG backtest"
    top_k: int = Field(default=3, ge=1, le=20)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=1000)


class AgentQuery(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=12)


class OverrideRequest(BaseModel):
    new_status: str = Field(pattern=r"^(APPROVE|REVIEW|REJECT)$")
    reason: str = Field(min_length=10, max_length=1000)
    actor: str = Field(default="loan-officer", min_length=2, max_length=160)
