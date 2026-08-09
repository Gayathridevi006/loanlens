"""
Loan Eligibility Engine — Scoring, risk assessment, and eligibility calculation.
Pure Python, no ML — fully rule-based and auditable.
"""

import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


# ── Data Structures ────────────────────────────────────────────────────────────

@dataclass
class DocumentsSummary:
    has_salary_slip:      bool = False
    has_bank_statement:   bool = False
    has_form_16:          bool = False
    has_cancelled_cheque: bool = False
    has_address_proof:    bool = False
    has_itr:              bool = False
    has_pan_card:         bool = False
    salary_slip_count:    int  = 0
    bank_statement_count: int  = 0


@dataclass
class IncomeProfile:
    net_monthly_salary:   float = 0.0
    gross_monthly_salary: float = 0.0
    annual_income:        float = 0.0
    tds_paid:             float = 0.0
    bank_closing_balance: float = 0.0
    bank_opening_balance: float = 0.0
    total_bank_credits:   float = 0.0
    total_bank_debits:    float = 0.0


@dataclass
class ScoreBreakdown:
    doc_completeness:  int = 0   # max 30
    income_strength:   int = 0   # max 30
    bank_health:       int = 0   # max 20
    tax_compliance:    int = 0   # max 10
    address_verified:  int = 0   # max 10
    total:             int = 0   # max 100


@dataclass
class LoanAssessment:
    score:               int
    risk_level:          str   # LOW | MEDIUM | HIGH | VERY_HIGH
    status:              str   # APPROVED | CONDITIONAL | REVIEW_REQUIRED | REJECTED
    recommendation:      str
    max_eligible_loan:   str
    suggested_emi:       str
    monthly_income:      str
    annual_income:       str
    bank_balance:        str
    doc_completeness:    str
    score_breakdown:     dict
    docs_submitted:      dict
    strengths:           list[str]
    issues:              list[str]
    missing_documents:   list[str]
    next_steps:          list[str]


# ── Parsing Helpers ────────────────────────────────────────────────────────────

def _parse_amount(val: Optional[str]) -> float:
    """Convert formatted amount string to float."""
    if not val:
        return 0.0
    cleaned = re.sub(r"[₹$€£,\s%]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ── Main Engine ────────────────────────────────────────────────────────────────

class LoanEligibilityEngine:
    """
    Comprehensive rule-based loan eligibility assessment.

    Scoring model (100 points total):
    ├── Document Completeness  30 pts
    ├── Income Strength        30 pts
    ├── Bank Health            20 pts
    ├── Tax Compliance         10 pts
    └── Address Verified       10 pts
    """

    # Loan multipliers by type
    LOAN_MULTIPLIERS = {
        "personal":  50,    # 50x monthly salary
        "home":      120,   # 120x monthly salary (10 years)
        "vehicle":   72,    # 72x monthly salary (6 years)
        "business":  60,
        "education": 84,
    }

    # EMI as % of net income (standard 40% FOIR)
    FOIR = 0.40

    @classmethod
    def assess(cls, documents: list[dict], loan_type: str = "personal") -> dict:
        """
        Run full eligibility assessment on a list of processed documents.

        Args:
            documents: List of doc records with {doc_type, fields}
            loan_type: Type of loan being applied for

        Returns:
            Assessment dict ready for API response
        """
        docs_summary = DocumentsSummary()
        income = IncomeProfile()
        strengths = []
        issues = []

        # ── Step 1: Aggregate data from all documents ──────────────────────────
        for doc in documents:
            dtype = doc.get("doc_type", "unknown")
            f = doc.get("fields", {})
            cls._process_document(dtype, f, docs_summary, income, strengths)

        # ── Step 2: Calculate score ────────────────────────────────────────────
        breakdown = cls._calculate_score(docs_summary, income)

        # ── Step 3: Determine risk & status ───────────────────────────────────
        risk, status, recommendation = cls._determine_risk(breakdown.total, docs_summary)

        # ── Step 4: Loan eligibility ───────────────────────────────────────────
        multiplier = cls.LOAN_MULTIPLIERS.get(loan_type, 50)
        monthly = income.net_monthly_salary or income.gross_monthly_salary * 0.8
        max_loan = monthly * multiplier
        max_emi = monthly * cls.FOIR

        # ── Step 5: Issues & next steps ───────────────────────────────────────
        missing = cls._missing_docs(docs_summary)
        issues = cls._build_issues(docs_summary, income)
        next_steps = cls._next_steps(status, missing)

        return {
            "score":             breakdown.total,
            "risk_level":        risk,
            "status":            status,
            "recommendation":    recommendation,
            "max_eligible_loan": f"₹{max_loan:,.0f}" if max_loan else "N/A",
            "suggested_emi":     f"₹{max_emi:,.0f}/month" if max_emi else "N/A",
            "monthly_income":    f"₹{monthly:,.0f}" if monthly else "N/A",
            "annual_income":     f"₹{income.annual_income or monthly * 12:,.0f}" if monthly else "N/A",
            "bank_balance":      f"₹{income.bank_closing_balance:,.0f}" if income.bank_closing_balance else "N/A",
            "doc_completeness":  f"{breakdown.doc_completeness * 10 // 3}%",
            "score_breakdown": {
                "doc_completeness": {"score": breakdown.doc_completeness, "max": 30},
                "income_strength":  {"score": breakdown.income_strength,  "max": 30},
                "bank_health":      {"score": breakdown.bank_health,       "max": 20},
                "tax_compliance":   {"score": breakdown.tax_compliance,    "max": 10},
                "address_verified": {"score": breakdown.address_verified,  "max": 10},
                "total":            {"score": breakdown.total,             "max": 100},
            },
            "docs_submitted": {
                "salary_slip":      docs_summary.has_salary_slip,
                "bank_statement":   docs_summary.has_bank_statement,
                "form_16":          docs_summary.has_form_16,
                "cancelled_cheque": docs_summary.has_cancelled_cheque,
                "address_proof":    docs_summary.has_address_proof,
                "itr":              docs_summary.has_itr,
            },
            "strengths":        strengths,
            "issues":           issues,
            "missing_documents": missing,
            "next_steps":       next_steps,
        }

    @classmethod
    def _process_document(cls, dtype: str, fields: dict,
                           ds: DocumentsSummary, ip: IncomeProfile,
                           strengths: list) -> None:
        """Extract income & doc flags from a single document."""

        if dtype == "salary_slip":
            ds.has_salary_slip = True
            ds.salary_slip_count += 1
            net = _parse_amount(fields.get("net_salary"))
            gross = _parse_amount(fields.get("gross_earnings"))
            if net > ip.net_monthly_salary:
                ip.net_monthly_salary = net
            if gross > ip.gross_monthly_salary:
                ip.gross_monthly_salary = gross
            if net:
                strengths.append(f"Net monthly salary verified: ₹{net:,.0f}")
            if fields.get("days_present"):
                strengths.append(f"Employment active: {fields['days_present']} days present")

        elif dtype == "bank_statement":
            ds.has_bank_statement = True
            ds.bank_statement_count += 1
            closing = _parse_amount(fields.get("closing_balance"))
            opening = _parse_amount(fields.get("opening_balance"))
            credits = _parse_amount(fields.get("total_credits"))
            debits  = _parse_amount(fields.get("total_debits"))
            if closing > ip.bank_closing_balance:
                ip.bank_closing_balance = closing
            if opening > ip.bank_opening_balance:
                ip.bank_opening_balance = opening
            if credits:
                ip.total_bank_credits += credits
            if debits:
                ip.total_bank_debits += debits
            if closing:
                strengths.append(f"Bank balance verified: ₹{closing:,.0f}")
            if fields.get("bank_name"):
                strengths.append(f"Account at {fields['bank_name']}")

        elif dtype == "form_16":
            ds.has_form_16 = True
            tds = _parse_amount(fields.get("total_tds"))
            ann = _parse_amount(fields.get("gross_salary"))
            if tds:
                ip.tds_paid = tds
                strengths.append(f"TDS compliance verified: ₹{tds:,.0f} deducted")
            if ann:
                ip.annual_income = ann
                strengths.append(f"Annual income per Form 16: ₹{ann:,.0f}")
            if fields.get("assessment_year"):
                strengths.append(f"Assessment year: {fields['assessment_year']}")

        elif dtype == "cancelled_cheque":
            ds.has_cancelled_cheque = True
            bank = fields.get("bank_name") or "bank"
            acct = fields.get("account_number", "")
            strengths.append(f"Bank account verified ({bank})")

        elif dtype == "utility_bill":
            ds.has_address_proof = True
            addr = fields.get("address") or fields.get("city_state_zip") or ""
            strengths.append(f"Address proof confirmed via utility bill")

        elif dtype == "income_tax_return":
            ds.has_itr = True
            inc = _parse_amount(fields.get("gross_total_income"))
            if inc:
                ip.annual_income = max(ip.annual_income, inc)
                strengths.append(f"ITR gross income: ₹{inc:,.0f}")
            strengths.append("ITR filed — strong income compliance signal")

        elif dtype == "pan_card":
            ds.has_pan_card = True
            strengths.append("PAN card on file — KYC identity anchor")

    @classmethod
    def _calculate_score(cls, ds: DocumentsSummary, ip: IncomeProfile) -> ScoreBreakdown:
        b = ScoreBreakdown()

        # ── Document Completeness (30 pts) ─────────────────────────────────────
        b.doc_completeness += 10 if ds.has_salary_slip else 0
        b.doc_completeness += 10 if ds.has_bank_statement else 0
        b.doc_completeness += 5  if ds.has_form_16 else 0
        b.doc_completeness += 3  if ds.has_cancelled_cheque else 0
        b.doc_completeness += 2  if ds.has_itr else 0
        b.doc_completeness = min(30, b.doc_completeness)

        # ── Income Strength (30 pts) ───────────────────────────────────────────
        net = ip.net_monthly_salary
        gross = ip.gross_monthly_salary
        income = net or gross * 0.8

        if income >= 100_000:   b.income_strength = 30
        elif income >= 75_000:  b.income_strength = 25
        elif income >= 50_000:  b.income_strength = 20
        elif income >= 30_000:  b.income_strength = 15
        elif income >= 15_000:  b.income_strength = 10
        elif income >= 5_000:   b.income_strength = 5
        # Bonus for multiple salary slips
        if ds.salary_slip_count >= 3:
            b.income_strength = min(30, b.income_strength + 3)

        # ── Bank Health (20 pts) ───────────────────────────────────────────────
        bal = ip.bank_closing_balance
        if bal >= 500_000:      b.bank_health = 20
        elif bal >= 200_000:    b.bank_health = 15
        elif bal >= 100_000:    b.bank_health = 12
        elif bal >= 50_000:     b.bank_health = 8
        elif bal >= 10_000:     b.bank_health = 5
        elif bal > 0:           b.bank_health = 2

        # Check credit/debit ratio
        if ip.total_bank_credits > 0 and ip.total_bank_debits > 0:
            ratio = ip.total_bank_credits / ip.total_bank_debits
            if ratio >= 1.2:
                b.bank_health = min(20, b.bank_health + 3)   # Healthy inflows

        # ── Tax Compliance (10 pts) ────────────────────────────────────────────
        if ds.has_form_16:
            b.tax_compliance += 6
        if ds.has_itr:
            b.tax_compliance += 4
        b.tax_compliance = min(10, b.tax_compliance)

        # ── Address Verified (10 pts) ──────────────────────────────────────────
        if ds.has_address_proof:
            b.address_verified = 10

        b.total = (b.doc_completeness + b.income_strength +
                   b.bank_health + b.tax_compliance + b.address_verified)
        return b

    @classmethod
    def _determine_risk(cls, score: int, ds: DocumentsSummary) -> tuple[str, str, str]:
        if score >= 80:
            return ("LOW",
                    "APPROVED",
                    "Strong profile. All key documents present. Recommend standard loan terms.")
        elif score >= 65:
            return ("LOW",
                    "APPROVED",
                    "Good profile. Proceed with loan subject to final verification.")
        elif score >= 50:
            return ("MEDIUM",
                    "CONDITIONAL",
                    "Acceptable profile. Request 3-month bank statements and recent salary slips.")
        elif score >= 35:
            return ("HIGH",
                    "REVIEW_REQUIRED",
                    "Incomplete documentation or borderline income. Senior review recommended.")
        else:
            return ("VERY_HIGH",
                    "REJECTED",
                    "Insufficient income evidence or critical documents missing. Resubmit with complete documentation.")

    @staticmethod
    def _missing_docs(ds: DocumentsSummary) -> list[str]:
        missing = []
        if not ds.has_salary_slip:
            missing.append("Salary Slip (last 3 months)")
        if not ds.has_bank_statement:
            missing.append("Bank Statement (last 6 months)")
        if not ds.has_form_16:
            missing.append("Form 16 / TDS Certificate")
        if not ds.has_cancelled_cheque:
            missing.append("Cancelled Cheque")
        if not ds.has_address_proof:
            missing.append("Address Proof (Utility Bill)")
        return missing

    @staticmethod
    def _build_issues(ds: DocumentsSummary, ip: IncomeProfile) -> list[str]:
        issues = []
        if not ds.has_salary_slip:
            issues.append("Income cannot be verified — salary slip required")
        if not ds.has_bank_statement:
            issues.append("Cash flow not assessed — bank statement missing")
        if not ds.has_form_16:
            issues.append("Tax compliance unverified — Form 16 missing")
        if not ds.has_cancelled_cheque:
            issues.append("Bank account details unverified — cancelled cheque missing")
        if not ds.has_address_proof:
            issues.append("Current address unverified — utility bill or rental agreement needed")
        if ip.net_monthly_salary < 15_000 and ip.net_monthly_salary > 0:
            issues.append(f"Low income detected (₹{ip.net_monthly_salary:,.0f}/month) — may affect eligibility")
        if ip.bank_closing_balance < 5_000 and ip.bank_closing_balance > 0:
            issues.append("Low bank balance — insufficient liquid reserves")
        return issues

    @staticmethod
    def _next_steps(status: str, missing: list[str]) -> list[str]:
        steps = []
        if missing:
            steps.append(f"Upload missing documents: {', '.join(missing)}")
        if status == "APPROVED":
            steps.extend([
                "Proceed to credit bureau check (CIBIL/Experian)",
                "Collect applicant signature on loan agreement",
                "Disburse loan within 3 working days",
            ])
        elif status == "CONDITIONAL":
            steps.extend([
                "Request additional income proof (3-month salary slips)",
                "Verify employer details via HR letter",
                "Re-assess after document submission",
            ])
        elif status == "REVIEW_REQUIRED":
            steps.extend([
                "Escalate to senior credit officer",
                "Request guarantor details",
                "Consider lower loan amount",
            ])
        else:
            steps.extend([
                "Inform applicant of rejection with specific reasons",
                "Suggest reapplication after 3-6 months with complete documents",
            ])
        return steps
