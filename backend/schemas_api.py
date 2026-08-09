from datetime import datetime
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
