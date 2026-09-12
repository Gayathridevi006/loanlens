"""Project-owned, offline models used by the loan decision service.

These models never read API keys and never send applicant data over the network.
The small sentiment classifier is fitted from the labelled examples below when
the service starts.  Risk and fraud models are explicit linear scorecards so
their contribution to a decision remains auditable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


SENTIMENT_TRAINING_DATA = (
    ("stable employment and regular salary credits", "POSITIVE"),
    ("excellent repayment history and reliable income", "POSITIVE"),
    ("good account conduct with positive business growth", "POSITIVE"),
    ("all instalments paid on time", "POSITIVE"),
    ("income is stable and obligations are manageable", "POSITIVE"),
    ("late payments and overdue instalments", "NEGATIVE"),
    ("customer defaulted after losing employment", "NEGATIVE"),
    ("urgent complaint about declining income", "NEGATIVE"),
    ("irregular salary and repeated repayment delays", "NEGATIVE"),
    ("business loss and unpaid debt", "NEGATIVE"),
    ("application received for assessment", "NEUTRAL"),
    ("documents were submitted by the applicant", "NEUTRAL"),
    ("requested a personal loan", "NEUTRAL"),
    ("bank statement covers the last six months", "NEUTRAL"),
    ("employment information is attached", "NEUTRAL"),
)


@dataclass(frozen=True)
class ScorecardResult:
    score: float
    reasons: tuple[str, ...]


class LocalSentimentModel:
    """A compact TF-IDF + logistic-regression classifier trained in-process."""

    def __init__(self) -> None:
        texts, labels = zip(*SENTIMENT_TRAINING_DATA)
        self.pipeline = Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                ("classifier", LogisticRegression(max_iter=500, random_state=42)),
            ]
        )
        self.pipeline.fit(texts, labels)

    def predict(self, text: str) -> tuple[str, float, list[str]]:
        cleaned = (text or "").strip()
        if not cleaned:
            return "NEUTRAL", 1.0, []
        probabilities = self.pipeline.predict_proba([cleaned])[0]
        classes = self.pipeline.classes_
        best = int(probabilities.argmax())
        vectorizer = self.pipeline.named_steps["tfidf"]
        tokens = vectorizer.build_analyzer()(cleaned)
        vocabulary = vectorizer.vocabulary_
        evidence = sorted({token for token in tokens if token in vocabulary}, key=len, reverse=True)[:6]
        return str(classes[best]), round(float(probabilities[best]), 4), evidence


class LocalLoanScorecards:
    """Transparent local risk/fraud models with bounded 0-100 outputs."""

    @staticmethod
    def fraud(income: float, amount: float, years: float, has_employer: bool,
              duplicate: bool) -> ScorecardResult:
        score, reasons = 8.0, []
        if income <= 0:
            score += 33
            reasons.append("Income could not be verified")
        if income > 10_000_000:
            score += 18
            reasons.append("Income is an unusual outlier")
        if amount > max(income * 8, 1_000_000):
            score += 18
            reasons.append("Requested amount is high relative to income")
        if duplicate:
            score += 18
            reasons.append("Possible duplicate application")
        if not has_employer and years > 0:
            score += 18
            reasons.append("Employer evidence is missing")
        return ScorecardResult(min(100.0, score), tuple(reasons))

    @staticmethod
    def credit_risk(credit: int, dti: float, existing: int, years: float,
                    income: float, fraud: float) -> ScorecardResult:
        score = 30 + max(0, 700 - credit) * .12 + max(0, dti - 30) * .55
        score += existing * 5 + fraud * .22
        score -= min(12, years * 1.2) + (6 if income > 600_000 else 0)
        reasons = (f"Credit score {credit}", f"Debt-to-income ratio {dti:.1f}%")
        return ScorecardResult(round(max(1, min(99, score)), 1), reasons)


@dataclass(frozen=True)
class AnomalyResult:
    available: bool
    anomalous: bool
    score: float
    confidence: float
    model_version: str
    reason: str


class LocalFraudAnomalyModel:
    """Load the trained Isolation Forest and score live applications locally."""

    FEATURE_ALIASES = {
        "Age": ("age",),
        "Experience": ("employment_years", "experience"),
        "Income": ("income", "annual_income"),
        "ZIP Code": ("zip_code", "postal_code", "pincode"),
        "Family": ("family", "family_size", "dependants"),
        "CCAvg": ("cc_avg", "credit_card_average"),
        "Education": ("education", "education_level"),
        "Mortgage": ("mortgage", "mortgage_amount"),
        "Securities Account": ("securities_account",),
        "CD Account": ("cd_account",),
        "Online": ("online_banking", "online"),
        "CreditCard": ("credit_card",),
    }

    def __init__(self) -> None:
        path = Path(__file__).resolve().parents[1] / "models" / "fraud_isolation_forest.joblib"
        self.path = path
        self.bundle = None
        if path.exists():
            try:
                self.bundle = joblib.load(path)
            except Exception:
                self.bundle = None

    def predict(self, record: dict) -> AnomalyResult:
        if not self.bundle:
            return AnomalyResult(False, False, 0, 0, "unavailable", "Isolation Forest artifact is not installed")
        features = self.bundle["features"]
        row, supplied = {}, 0
        for feature in features:
            value = None
            for alias in self.FEATURE_ALIASES.get(feature, (feature,)):
                if record.get(alias) not in (None, ""):
                    try:
                        value = float(record[alias])
                        supplied += 1
                    except (TypeError, ValueError):
                        pass
                    break
            if feature == "Income" and value is not None and value > 10_000:
                value /= 12_000  # annual INR to the training workbook's monthly ₹000 unit
            row[feature] = value
        frame = pd.DataFrame([row], columns=features)
        margin = float(self.bundle["pipeline"].decision_function(frame)[0])
        anomalous = int(self.bundle["pipeline"].predict(frame)[0]) == -1
        score = round(100 / (1 + math.exp(12 * margin)), 1)
        confidence = round(supplied / max(len(features), 1), 3)
        version = f"isolation-forest-{self.path.stat().st_mtime_ns:x}"
        reason = f"Isolation Forest {'flagged an anomaly' if anomalous else 'found the profile within its learned range'} with {supplied}/{len(features)} model features supplied"
        return AnomalyResult(True, anomalous, score, confidence, version, reason)


sentiment_model = LocalSentimentModel()
loan_scorecards = LocalLoanScorecards()
fraud_anomaly_model = LocalFraudAnomalyModel()
fraud_anomaly_model = LocalFraudAnomalyModel()
