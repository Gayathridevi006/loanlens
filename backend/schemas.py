"""
Data schemas for request/response validation.
Uses Python dataclasses (no external deps). 
Swap to Pydantic for stricter validation in production.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
import uuid


# ── Request Schemas ────────────────────────────────────────────────────────────

@dataclass
class CreateApplicationRequest:
    applicant_name: str
    loan_type: str = "personal"             # personal | home | vehicle | business | education
    loan_amount: float = 0.0
    applicant_phone: Optional[str] = None
    applicant_email: Optional[str] = None
    applicant_pan:   Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "CreateApplicationRequest":
        return cls(
            applicant_name=d.get("applicant_name", ""),
            loan_type=d.get("loan_type", "personal"),
            loan_amount=float(d.get("loan_amount", 0)),
            applicant_phone=d.get("applicant_phone"),
            applicant_email=d.get("applicant_email"),
            applicant_pan=d.get("applicant_pan"),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.applicant_name.strip():
            errors.append("applicant_name is required")
        if self.loan_type not in ("personal", "home", "vehicle", "business", "education"):
            errors.append(f"Invalid loan_type: {self.loan_type}")
        if self.loan_amount < 0:
            errors.append("loan_amount must be non-negative")
        return errors


@dataclass
class UploadDocumentRequest:
    image_b64: str
    application_id: Optional[str] = None
    filename: Optional[str] = None
    override_doc_type: Optional[str] = None  # Manual override for classification

    @classmethod
    def from_dict(cls, d: dict) -> "UploadDocumentRequest":
        return cls(
            image_b64=d.get("image_b64", ""),
            application_id=d.get("application_id"),
            filename=d.get("filename"),
            override_doc_type=d.get("override_doc_type"),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.image_b64:
            errors.append("image_b64 is required")
        return errors


# ── Domain Models ──────────────────────────────────────────────────────────────

@dataclass
class DocumentRecord:
    doc_id:            str
    doc_type:          str
    doc_type_label:    str
    fields:            dict
    raw_text_preview:  str
    confidence:        str        # HIGH | MEDIUM | LOW
    confidence_score:  float
    matched_patterns:  list[str]
    processed_at:      str
    filename:          Optional[str] = None
    page_count:        int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def create(cls, doc_type: str, doc_type_label: str, fields: dict,
               raw_text: str, confidence: str, confidence_score: float,
               matched_patterns: list[str], filename: str = None) -> "DocumentRecord":
        return cls(
            doc_id=str(uuid.uuid4())[:8].upper(),
            doc_type=doc_type,
            doc_type_label=doc_type_label,
            fields=fields,
            raw_text_preview=raw_text[:600],
            confidence=confidence,
            confidence_score=confidence_score,
            matched_patterns=matched_patterns,
            processed_at=datetime.utcnow().isoformat(),
            filename=filename,
        )


@dataclass
class LoanApplication:
    id:                      str
    applicant_name:          str
    loan_type:               str
    loan_amount_requested:   float
    applicant_phone:         Optional[str]
    applicant_email:         Optional[str]
    applicant_pan:           Optional[str]
    created_at:              str
    updated_at:              str
    status:                  str              # pending | under_review | approved | rejected
    documents:               list[dict] = field(default_factory=list)
    assessment:              Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def create(cls, req: CreateApplicationRequest) -> "LoanApplication":
        now = datetime.utcnow().isoformat()
        return cls(
            id=str(uuid.uuid4())[:8].upper(),
            applicant_name=req.applicant_name,
            loan_type=req.loan_type,
            loan_amount_requested=req.loan_amount,
            applicant_phone=req.applicant_phone,
            applicant_email=req.applicant_email,
            applicant_pan=req.applicant_pan,
            created_at=now,
            updated_at=now,
            status="pending",
        )

    def add_document(self, doc: DocumentRecord) -> None:
        self.documents.append(doc.to_dict())
        self.updated_at = datetime.utcnow().isoformat()

    def update_status(self, new_status: str) -> None:
        self.status = new_status
        self.updated_at = datetime.utcnow().isoformat()


# ── Response Helpers ───────────────────────────────────────────────────────────

def success_response(data: dict, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


def error_response(message: str, code: int = 400) -> dict:
    return {"status": "error", "message": message, "code": code}


def paginate(items: list, page: int = 1, per_page: int = 20) -> dict:
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }
