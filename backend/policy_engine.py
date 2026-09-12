"""Versioned lending-policy corpus and deterministic compliance controls."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .agentic_rag import EvidenceChunk
from .rag_evaluation import retrieve


POLICY_VERSION = "loanlens-policy-2026.09"
POLICIES = [
    {
        "id": "POL-DOC-001",
        "section": "Document completeness",
        "text": "Personal loan review requires recent income evidence, a bank statement, and identity evidence before final approval.",
    },
    {
        "id": "POL-FRAUD-001",
        "section": "Fraud escalation",
        "text": "Applications with material identity, income, duplicate-document, or tampering signals require manual fraud review.",
    },
    {
        "id": "POL-RISK-001",
        "section": "Risk decision bands",
        "text": "Credit risk at or above 70 or fraud risk at or above 75 produces a reject recommendation subject to officer review.",
    },
    {
        "id": "POL-HITL-001",
        "section": "Human oversight",
        "text": "LoanLens recommendations are advisory. An authorized loan officer owns the final decision and must record an override reason.",
    },
    {
        "id": "POL-FAIR-001",
        "section": "Fair lending",
        "text": "Protected attributes must not be model features. Governance reviewers monitor selection rates and investigate material disparities.",
    },
]

REQUIRED_DOCUMENTS = {
    "personal": {"bank_statement", "income_evidence", "identity_evidence"},
    "home": {"bank_statement", "income_evidence", "identity_evidence", "address_proof"},
    "car": {"bank_statement", "income_evidence", "identity_evidence"},
    "vehicle": {"bank_statement", "income_evidence", "identity_evidence"},
    "education": {"bank_statement", "income_evidence", "identity_evidence"},
    "business": {"bank_statement", "income_evidence", "identity_evidence"},
    "gold": {"identity_evidence", "address_proof"},
}

CATEGORY_TYPES = {
    "bank_statement": {"bank_statement"},
    "income_evidence": {"salary_slip", "income_tax_return", "form_16", "itr"},
    "identity_evidence": {"pan_card", "aadhaar", "kyc"},
    "address_proof": {"utility_bill", "aadhaar"},
}


def retrieve_policies(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    ranked = retrieve(query, [{"id": item["id"], "text": item["text"]} for item in POLICIES], top_k)
    by_id = {item["id"]: item for item in POLICIES}
    return [
        {
            **item,
            "source": "lending-policy",
            "document_type": "policy",
            "section": by_id[item["id"]]["section"],
            "page": None,
            "fields": {"policy_version": POLICY_VERSION},
        }
        for item in ranked
    ]


def assess_documents(record: dict[str, Any], evidence: list[EvidenceChunk]) -> dict[str, Any]:
    loan_type = str(record.get("loan_type") or "personal").lower().replace(" loan", "").strip()
    required = REQUIRED_DOCUMENTS.get(loan_type, REQUIRED_DOCUMENTS["personal"])
    submitted_types = {chunk.document_type.lower().replace(" ", "_") for chunk in evidence if chunk.source != "application-profile"}
    present_categories = {
        category for category, types in CATEGORY_TYPES.items() if submitted_types & types
    }
    missing = sorted(required - present_categories)
    expired, low_confidence = [], []
    today = date.today()
    freshness_days = {"salary_slip": 120, "bank_statement": 210, "utility_bill": 120}
    for chunk in evidence:
        doc_type = chunk.document_type.lower().replace(" ", "_")
        confidence = chunk.fields.get("classification_confidence")
        if confidence not in (None, "") and float(confidence) < 0.2:
            low_confidence.append(chunk.id)
        for field_name in ("statement_date", "bill_date", "filing_date", "date"):
            raw = chunk.fields.get(field_name)
            if not raw or doc_type not in freshness_days:
                continue
            parsed = None
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
                try:
                    parsed = datetime.strptime(str(raw), fmt).date()
                    break
                except ValueError:
                    pass
            if parsed and (today - parsed).days > freshness_days[doc_type]:
                expired.append({"evidence_id": chunk.id, "document_type": doc_type, "date": str(parsed)})
    return {
        "policy_version": POLICY_VERSION,
        "loan_type": loan_type,
        "submitted_document_types": sorted(submitted_types),
        "missing_categories": missing,
        "expired_documents": expired,
        "low_confidence_documents": sorted(set(low_confidence)),
        "complete": not missing and not expired and not low_confidence,
    }


def adverse_action_reasons(risk_score: float, fraud: dict[str, Any], document_assessment: dict[str, Any]) -> list[dict[str, str]]:
    reasons = []
    if risk_score >= 70:
        reasons.append({"code": "AA-CREDIT-RISK", "description": "Credit risk exceeds the configured policy threshold."})
    for signal in fraud["signals"]:
        if signal["severity"] in {"HIGH", "CRITICAL"}:
            reasons.append({"code": f"AA-{signal['code']}", "description": signal["description"]})
    if document_assessment["missing_categories"]:
        reasons.append({"code": "AA-INCOMPLETE-DOCUMENTS", "description": "Required application evidence is incomplete."})
    return reasons
