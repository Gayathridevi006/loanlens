"""
Document Classifier — Rule-based classification using regex pattern matching.
No ML model required. Pattern weights allow confidence scoring.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    doc_type: str
    doc_type_label: str
    confidence_score: float        # 0.0 – 1.0
    matched_patterns: list[str]

    @property
    def confidence_label(self) -> str:
        if self.confidence_score >= 0.6:
            return "HIGH"
        elif self.confidence_score >= 0.3:
            return "MEDIUM"
        return "LOW"

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "doc_type_label": self.doc_type_label,
            "confidence_score": round(self.confidence_score, 2),
            "confidence_label": self.confidence_label,
            "matched_patterns": self.matched_patterns,
        }


# ── Pattern Registry ───────────────────────────────────────────────────────────
# Each entry: (pattern, weight)
# Higher weight = stronger signal for that doc type

DOC_PATTERNS: dict[str, list[tuple[str, float]]] = {

    "salary_slip": [
        (r"salary\s*slip",                   3.0),
        (r"pay\s*slip|payslip",               3.0),
        (r"net\s*salary",                     2.5),
        (r"gross\s*salary",                   2.0),
        (r"basic\s*(?:pay|salary)",           2.0),
        (r"total\s*earnings",                 2.0),
        (r"total\s*deductions?",              1.5),
        (r"pf\s*no|provident\s*fund",         1.5),
        (r"employee\s*(?:code|id|no)",        1.5),
        (r"hra|house\s*rent\s*allow",         1.5),
        (r"days?\s*present|days?\s*absent",   1.5),
        (r"esi|e\.s\.i",                      1.0),
        (r"income\s*tax\s*deducted",          1.0),
        (r"for\s+enkay|enkay\s+telecom",      1.5),  # Sample data specific
    ],

    "bank_statement": [
        (r"(?:account|bank)\s*statement",     3.0),
        (r"opening\s*balance",                2.5),
        (r"closing\s*balance",                2.5),
        (r"debit.*credit.*balance",           2.0),
        (r"money\s*in|money\s*out",           2.0),
        (r"sort\s*code",                      2.0),
        (r"transactions?",                    1.5),
        (r"ifsc|swift\s*code|iban|bic",       1.5),
        (r"account\s*number",                 1.5),
        (r"balance\s*b/f|balance\s*carried",  1.5),
        (r"direct\s*debit|standing\s*order",  1.0),
        (r"hsbc|natwest|barclays|lloyds",     1.0),
        (r"hdfc|icici|axis|sbi|pnb",          1.0),
        (r"current\s*account|savings?\s*(?:account)?", 1.0),
    ],

    "form_16": [
        (r"form\s*(?:no\.?\s*)?16",           4.0),
        (r"tds\s*certificate",                3.0),
        (r"traces",                           2.5),
        (r"assessment\s*year",                2.5),
        (r"certificate.*income\s*tax",        2.5),
        (r"section\s*203",                    2.5),
        (r"pan.*(?:deductor|deductee)",       2.0),
        (r"tan.*(?:deductor|deductee)",       2.0),
        (r"income\s*tax\s*deducted\s*at\s*source", 2.0),
        (r"acknowledgement\s*(?:no|number)",  1.5),
        (r"quarterly\s*statements?",          1.5),
        (r"salary\s*paid",                    1.0),
        (r"gross\s*total\s*income",           1.5),
        (r"deductions?\s*under\s*chapter",    2.0),
    ],

    "utility_bill": [
        (r"gas\s*(?:bill|south|charges)",     3.0),
        (r"electricity\s*bill",               3.0),
        (r"water\s*bill",                     3.0),
        (r"consumption\s*history",            2.5),
        (r"meter\s*(?:read|end|start)",       2.5),
        (r"units?\s*consumed",                2.5),
        (r"amount\s*due",                     2.0),
        (r"bill\s*date",                      2.0),
        (r"due\s*date",                       1.5),
        (r"rate\s*plan",                      1.5),
        (r"therm(?:s)?",                      2.0),   # Gas bills
        (r"kwh|kilowatt",                     2.0),   # Electricity bills
        (r"account\s*number.*\d{6,}",         1.0),
        (r"previous\s*balance",               1.0),
        (r"personal\s*message\s*center",      2.0),   # Gas South sample
    ],

    "cancelled_cheque": [
        (r"cancel+ed",                        4.0),
        (r"a/c\s*no|account\s*(?:no|number)", 2.0),
        (r"ifsc|ifs\s*code",                  2.0),
        (r"micr",                             2.0),
        (r"bearer|or\s*bearer",               2.0),
        (r"pay(?:\s+to\s+the\s+order)?",      1.5),
        (r"rupees|rs\.",                       1.5),
        (r"axis\s*bank|pnb|punjab\s*national", 1.5),
        (r"authorised\s*signator",            1.5),
        (r"payable\s*at\s*par",               1.5),
        (r"new\s*account",                    1.0),
        (r"savings?\s*a/c|savings?\s*account", 1.0),
    ],

    "income_tax_return": [
        (r"itr[-\s]*[1-7v]",                  4.0),
        (r"income\s*tax\s*return",            3.5),
        (r"e-filing\s*acknowledgement",       3.0),
        (r"gross\s*total\s*income",           2.0),
        (r"income\s*from\s*(?:salary|house|business)", 2.0),
        (r"refund\s*(?:due|amount)",          1.5),
        (r"(?:total\s*)?tax\s*payable",       1.5),
        (r"pan\s*no.*assessment",             2.0),
        (r"self\s*assessment\s*tax",          2.0),
    ],

    "pan_card": [
        (r"income\s*tax\s*department",        3.0),
        (r"permanent\s*account\s*number",     4.0),
        (r"[A-Z]{5}\d{4}[A-Z]",              2.0),
        (r"govt\.?\s*of\s*india",             1.5),
        (r"father.?s\s*name",                 1.5),
    ],

    "aadhaar": [
        (r"aadhaar|aadhar",                   4.0),
        (r"unique\s*identification",           3.0),
        (r"uidai",                            3.0),
        (r"\d{4}\s+\d{4}\s+\d{4}",           2.0),  # Aadhaar number format
        (r"dob.*\d{2}/\d{2}/\d{4}",          1.0),
    ],
}

LABELS = {
    "salary_slip":       "Salary Slip",
    "bank_statement":    "Bank Statement",
    "form_16":           "Form 16 / TDS Certificate",
    "utility_bill":      "Utility Bill",
    "cancelled_cheque":  "Cancelled Cheque",
    "income_tax_return": "Income Tax Return",
    "pan_card":          "PAN Card",
    "aadhaar":           "Aadhaar Card",
    "unknown":           "Unknown Document",
}


class DocumentClassifier:
    """
    Weighted pattern-matching document classifier.

    Scores each document type by summing weights of matched patterns,
    then normalises against the maximum possible score for that type.
    Returns the highest-scoring type with confidence metadata.
    """

    @classmethod
    def classify(cls, text: str) -> ClassificationResult:
        text_lower = text.lower()
        scores: dict[str, float] = {}
        all_matched: dict[str, list[str]] = {}

        for doc_type, patterns in DOC_PATTERNS.items():
            type_score = 0.0
            matched = []
            max_possible = sum(w for _, w in patterns)

            for pattern, weight in patterns:
                if re.search(pattern, text_lower):
                    type_score += weight
                    matched.append(pattern)

            if type_score > 0:
                # Normalise to 0–1 range
                scores[doc_type] = type_score / max_possible
                all_matched[doc_type] = matched

        if not scores:
            return ClassificationResult(
                doc_type="unknown",
                doc_type_label=LABELS["unknown"],
                confidence_score=0.0,
                matched_patterns=[],
            )

        best_type = max(scores, key=scores.get)
        return ClassificationResult(
            doc_type=best_type,
            doc_type_label=LABELS.get(best_type, best_type.replace("_", " ").title()),
            confidence_score=scores[best_type],
            matched_patterns=all_matched.get(best_type, []),
        )

    @classmethod
    def classify_all(cls, text: str) -> list[ClassificationResult]:
        """Return ranked list of all candidate types (useful for debugging)."""
        text_lower = text.lower()
        results = []

        for doc_type, patterns in DOC_PATTERNS.items():
            type_score = 0.0
            matched = []
            max_possible = sum(w for _, w in patterns)

            for pattern, weight in patterns:
                if re.search(pattern, text_lower):
                    type_score += weight
                    matched.append(pattern)

            if type_score > 0:
                results.append(ClassificationResult(
                    doc_type=doc_type,
                    doc_type_label=LABELS.get(doc_type, doc_type),
                    confidence_score=type_score / max_possible,
                    matched_patterns=matched,
                ))

        results.sort(key=lambda r: r.confidence_score, reverse=True)
        return results
