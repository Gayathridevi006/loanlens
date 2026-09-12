import json
from pathlib import Path
import pandas as pd

from .agentic_rag import run_agentic_assessment
from .classifier import DocumentClassifier
from .extractors import extract_fields
from .local_models import fraud_anomaly_model, loan_scorecards, sentiment_model

def sentiment(text: str):
    return sentiment_model.predict(text)

def score_record(record: dict):
    """Run the transparent baseline models before agent orchestration."""
    income = number(record, "income", "annual_income", "gross_total_income", "total_income", "Income")
    if income <= 0:
        income = number(record, "net_salary", "gross_earnings", "monthly_income") * 12
    amount = number(record, "loan_amount", "amount", default=max(100000, income * 2))
    credit = int(number(record, "credit_score", "cibil_score", default=650))
    dti = number(record, "dti", "debt_to_income", default=min(65, amount / max(income, 1) * 12))
    years = number(record, "employment_years", "experience", "Experience", default=2)
    existing = int(number(record, "existing_loans", default=0))
    comments = str(record.get("comments") or record.get("statement") or "")
    fraud_result = loan_scorecards.fraud(
        income, amount, years, bool(record.get("employer") or record.get("employer_name")), bool(record.get("duplicate"))
    )
    anomaly = fraud_anomaly_model.predict(record)
    anomaly_lift = max(0.0, anomaly.score - 50) * anomaly.confidence if anomaly.available and anomaly.anomalous else 0.0
    fraud = round(min(100.0, max(fraud_result.score, fraud_result.score + anomaly_lift)), 1)
    risk_result = loan_scorecards.credit_risk(credit, dti, existing, years, income, fraud)
    risk = risk_result.score
    status = "APPROVE" if risk < 40 and fraud < 40 else "REJECT" if risk >= 70 or fraud >= 75 else "REVIEW"
    sent, conf, keys = sentiment(comments)
    reasons = list(fraud_result.reasons) or ["No material rule-based fraud indicators found"]
    if anomaly.available:
        reasons.append(anomaly.reason)
    reasons += list(risk_result.reasons)
    summary = f"Applicant shows a {risk:.0f}/100 credit risk and {fraud:.0f}/100 fraud risk. "
    summary += f"The financial profile and {sent.lower()} narrative support a {status} recommendation."
    return dict(income=income, loan_amount=amount, credit_score=credit, dti=dti,
        employment_years=years, existing_loans=existing, comments=comments, status=status,
        risk_score=risk, fraud_score=fraud, sentiment=sent, sentiment_confidence=conf,
        explanation="; ".join(reasons), ai_summary=summary,
        processing_log=["Validated source fields", "Normalized numeric values", "Ran local fraud and credit scorecards", f"Ran live Isolation Forest ({anomaly.model_version})", "Ran locally trained sentiment model"])


def analyze(record: dict):
    """Run the live agentic RAG decision path used by intake and re-analysis."""
    base = score_record(record)
    report = run_agentic_assessment(record, base)
    decision = report["decision"]
    fraud = report["fraud_assessment"]
    signal_reasons = [signal["description"] for signal in fraud["signals"]]
    base.update(
        status=decision["recommendation"],
        fraud_score=decision["fraud_score"],
        explanation="; ".join(signal_reasons + [base["explanation"]]),
        ai_summary=report["answer"],
        processing_log=[
            "Validated and normalized source fields",
            f"Planned agent workflow for {report['plan']['intent']} intent",
            f"Retrieved {len(report['retrieved_evidence'])} grounded evidence chunks",
            f"Ran {len(fraud['checks_performed'])} fraud consistency checks",
            "Ran local credit-risk and sentiment models",
            f"Verified answer citations ({report['verification']['citation_coverage'] * 100:.0f}% coverage)",
            "Applied human-review decision guardrails",
        ],
    )
    return base

def number(d, *keys, default=0):
    for key in keys:
        if key in d and d[key] not in (None, ""):
            try: return float(str(d[key]).replace(",", "").replace("₹", ""))
            except (ValueError, TypeError): pass
    return float(default)

def parse_upload(path: Path):
    ext = path.suffix.lower()
    if ext == ".csv": return pd.read_csv(path).replace({float("nan"): None}).to_dict("records")
    if ext in (".xlsx", ".xls"): return pd.read_excel(path).replace({float("nan"): None}).to_dict("records")
    if ext == ".json":
        data = json.loads(path.read_text(errors="ignore")); return data if isinstance(data, list) else [data]
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            page_texts = [(page.extract_text() or "") for page in PdfReader(path).pages[:25]]
        except Exception:
            page_texts = []
        documents, merged_fields = [], {}
        for page_number, text in enumerate(page_texts, 1):
            classification = DocumentClassifier.classify(text)
            fields = {key: value for key, value in extract_fields(classification.doc_type, text).items() if value not in (None, "")}
            merged_fields.update({key: value for key, value in fields.items() if key not in merged_fields})
            documents.append({
                "filename": path.name,
                "data": {
                    **fields,
                    "comments": text[:8000],
                    "document_type": classification.doc_type,
                    "classification_confidence": classification.confidence_score,
                    "page": page_number,
                },
            })
        text = "\n".join(page_texts)
        primary_type = documents[0]["data"]["document_type"] if documents else "unknown"
        return [{
            "applicant_name": merged_fields.get("applicant_name") or merged_fields.get("employee_name") or path.stem[:80],
            "comments": text[:16000],
            "document_type": primary_type,
            "documents": documents,
            **merged_fields,
        }]
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        from .engine import OCREngine
        result = OCREngine.extract_from_path(path)
        classification = DocumentClassifier.classify(result.text)
        fields = {key: value for key, value in extract_fields(classification.doc_type, result.text).items() if value not in (None, "")}
        return [{
            "applicant_name": fields.get("applicant_name") or fields.get("employee_name") or path.stem[:80],
            "comments": result.text[:16000],
            "document_type": classification.doc_type,
            "classification_confidence": classification.confidence_score,
            "ocr_confidence": result.confidence,
            **fields,
        }]
    raise ValueError("Supported formats: CSV, XLSX, XLS, JSON, PDF, PNG, JPG and TIFF")
