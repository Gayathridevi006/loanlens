import json
from pathlib import Path
import pandas as pd

from .local_models import loan_scorecards, sentiment_model

def sentiment(text: str):
    return sentiment_model.predict(text)

def analyze(record: dict):
    income = number(record, "income", "annual_income", "Income")
    amount = number(record, "loan_amount", "amount", default=max(100000, income * 2))
    credit = int(number(record, "credit_score", "cibil_score", default=650))
    dti = number(record, "dti", "debt_to_income", default=min(65, amount / max(income, 1) * 12))
    years = number(record, "employment_years", "experience", "Experience", default=2)
    existing = int(number(record, "existing_loans", default=0))
    comments = str(record.get("comments") or record.get("statement") or "")
    fraud_result = loan_scorecards.fraud(
        income, amount, years, bool(record.get("employer")), bool(record.get("duplicate"))
    )
    fraud = fraud_result.score
    risk_result = loan_scorecards.credit_risk(credit, dti, existing, years, income, fraud)
    risk = risk_result.score
    status = "APPROVE" if risk < 40 and fraud < 40 else "REJECT" if risk >= 70 or fraud >= 75 else "REVIEW"
    sent, conf, keys = sentiment(comments)
    reasons = list(fraud_result.reasons) or ["No material fraud indicators found"]
    reasons += list(risk_result.reasons)
    summary = f"Applicant shows a {risk:.0f}/100 credit risk and {fraud:.0f}/100 fraud risk. "
    summary += f"The financial profile and {sent.lower()} narrative support a {status} recommendation."
    return dict(income=income, loan_amount=amount, credit_score=credit, dti=dti,
        employment_years=years, existing_loans=existing, comments=comments, status=status,
        risk_score=risk, fraud_score=fraud, sentiment=sent, sentiment_confidence=conf,
        explanation="; ".join(reasons), ai_summary=summary,
        processing_log=["Validated source fields", "Normalized numeric values", "Ran local fraud and credit scorecards", "Ran locally trained sentiment model"])

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
            text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages[:25])
        except Exception: text = ""
        return [{"applicant_name": path.stem[:80], "comments": text[:8000], "document_type": "PDF"}]
    raise ValueError("Supported formats: CSV, XLSX, XLS, JSON and PDF")
