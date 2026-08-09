"""
Field Extractors — Document-specific regex parsers.
Each extractor targets one document type and returns a typed dict.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _find(pattern: str, text: str, group: int = 1,
          flags: int = re.IGNORECASE) -> Optional[str]:
    """Return first capture group, stripped."""
    m = re.search(pattern, text, flags)
    if not m:
        return None
    try:
        val = m.group(group)
    except IndexError:
        val = m.group(0)
    return val.strip() if val else None


def _find_all(pattern: str, text: str,
              flags: int = re.IGNORECASE) -> list[str]:
    return re.findall(pattern, text, flags)


def _money(pattern: str, text: str, group: int = 1) -> Optional[str]:
    """Extract and format a monetary amount."""
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    try:
        raw = m.group(group)
    except IndexError:
        raw = m.group(0)
    if raw is None:
        return None
    cleaned = re.sub(r"[₹$€£,\s]", "", raw).strip()
    try:
        return f"₹{float(cleaned):,.2f}"
    except ValueError:
        return raw.strip()


def _date(pattern: str, text: str) -> Optional[str]:
    """Extract a date string."""
    return _find(pattern, text)


def _pan(text: str) -> Optional[str]:
    """Extract PAN number ([A-Z]{5}[0-9]{4}[A-Z])."""
    m = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", text)
    return m.group(0) if m else None


def _clean_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    # Remove trailing garbage (digits, special chars at end)
    cleaned = re.sub(r"[^A-Za-z\s\.]", "", raw).strip()
    return cleaned if len(cleaned) >= 3 else None


# ── Per-Document Extractors ────────────────────────────────────────────────────

class SalarySlipExtractor:
    @staticmethod
    def extract(text: str) -> dict:
        t = text

        # Multiple name patterns to handle varied formats
        employee_name = (
            _clean_name(_find(r"employee\s*name\s*[:\-=]?\s*([A-Z][A-Za-z\s\.]{3,40})", t))
            or _clean_name(_find(r"name\s*[:\-=]\s*([A-Z][A-Za-z\s\.]{3,40})", t))
        )

        return {
            "employee_name":   employee_name,
            "employee_id":     _find(r"employee\s*(?:code|id|no|number)\s*[:\-=]?\s*([\w\d\/]+)", t),
            "designation":     _clean_name(_find(r"designation\s*[:\-=]?\s*([A-Za-z\s]{3,40})", t)),
            "department":      _clean_name(_find(r"department\s*[:\-=]?\s*([A-Za-z\s]{3,30})", t)),
            "date_of_joining": _date(r"(?:date\s*of\s*joining|doj)\s*[:\-=]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", t),
            "month_year":      _find(r"(?:salary\s*for|month|period)\s*(?:of\s*)?[:\-]?\s*((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-,\']*\d{2,4})", t),
            "pf_number":       _find(r"pf\s*no[:\.\s]*([\w\d\/]+)", t),
            "uan_number":      _find(r"uan\s*(?:no|number)?\s*[:\-]?\s*(\d{12})", t),
            "pan_number":      _pan(t),

            # Earnings
            "basic_pay":       _money(r"(?:current\s*)?basic\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "hra":             _money(r"(?:current\s*)?hra\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "conveyance":      _money(r"(?:current\s*)?conv(?:eyance)?\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "da":              _money(r"(?:current\s*)?da\b\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "medical_allow":   _money(r"medical\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "education_allow": _money(r"education\s*(?:allow|allw)\.?\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "other_income":    _money(r"other\s*income\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "gross_earnings":  _money(r"(?:total\s*)?earnings\s*[:\-=₹]?\s*([\d,\.]+)", t),

            # Deductions
            "pf_deduction":    _money(r"(?:prov\.?\s*fund|provident\s*fund|p\.?f\.?)\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "esi":             _money(r"e\.?s\.?i\.?\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "fp_fund":         _money(r"f\.?p\.?\s*fund\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "prof_tax":        _money(r"prof(?:essional)?\s*tax\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "income_tax":      _money(r"income\s*tax\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "loan_deduction":  _money(r"loan\s*deduct(?:ion)?\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "total_deductions":_money(r"total\s*deduct\w*\s*[:\-=₹]?\s*([\d,\.]+)", t),
            "net_salary":      _money(r"net\s*salary\s*[:\-=₹]?\s*([\d,\.]+)", t),

            # Attendance
            "total_days":      _find(r"tot(?:al)?\.?\s*working\s*days\s*[:\-=]?\s*(\d+)", t),
            "days_absent":     _find(r"tot(?:al)?\.?\s*days?\s*absent\s*[:\-=]?\s*(\d+)", t),
            "days_present":    _find(r"tot(?:al)?\.?\s*days?\s*present\s*[:\-=]?\s*(\d+\.?\d*)", t),
        }


class BankStatementExtractor:
    @staticmethod
    def extract(text: str) -> dict:
        t = text
        return {
            "account_holder":   _clean_name(_find(r"(?:account\s*name|name)\s*[:\-]?\s*([A-Z][A-Za-z\s]{3,40})", t)),
            "account_number":   _find(r"(?:account\s*(?:no|number|#)|a/c\s*no)\s*[:\-]?\s*([\d\s\-]{6,20})", t),
            "bank_name":        _find(r"(HSBC|HDFC\s*Bank|SBI|ICICI\s*Bank|Axis\s*Bank|PNB|Punjab\s*National\s*Bank|Barclays|NatWest|Canara\s*Bank|Bank\s*of\s*Baroda)", t, flags=0),
            "ifsc_code":        _find(r"ifsc\s*(?:code)?\s*[:\-]?\s*([A-Z]{4}0[A-Z0-9]{6})", t),
            "swift_code":       _find(r"(?:swift|bic)\s*[:\-]?\s*([A-Z]{6}[A-Z0-9]{2,5})", t),
            "sort_code":        _find(r"sort\s*code\s*[:\-]?\s*(\d{2}[-\s]?\d{2}[-\s]?\d{2})", t),
            "iban":             _find(r"iban\s*[:\-]?\s*([A-Z]{2}\d{2}[A-Z0-9]{1,30})", t),
            "account_type":     _find(r"account\s*type\s*[:\-]?\s*([A-Za-z\/\s]{3,30})", t),
            "currency":         _find(r"(?:currency|account\s*currency)\s*[:\-]?\s*([A-Z]{3})", t),
            "opening_balance":  _money(r"opening\s*balance\s*[€\$₹]?\s*([\d,\.]+)", t),
            "closing_balance":  _money(r"closing\s*balance\s*[€\$₹]?\s*([\d,\.]+)", t),
            "total_credits":    _money(r"(?:payments?\s*in|total\s*credits?)\s*[€\$₹]?\s*([\d,\.]+)", t),
            "total_debits":     _money(r"(?:payments?\s*out|total\s*debits?)\s*[€\$₹]?\s*([\d,\.]+)", t),
            "statement_date":   _date(r"(?:statement\s*date|as\s*on)\s*[:\-]?\s*(\d{1,2}[\s\w]+\d{4})", t),
            "period_from":      _date(r"(?:from|period\s*from)\s*[:\-]?\s*(\d{1,2}[\/\-]\w+[\/\-]\d{2,4})", t),
            "address":          _find(r"(?:address|addr)\s*[:\-]?\s*(.{10,100}?)(?:\n\n|\d{6}|phone|tel)", t, flags=re.IGNORECASE | re.DOTALL),
        }


class Form16Extractor:
    @staticmethod
    def extract(text: str) -> dict:
        t = text
        return {
            "employee_name":    _clean_name(_find(r"name.*?(?:employee|deductee)\s*[:\-]?\s*([A-Z][A-Za-z\s\.]{3,40})", t)),
            "employer_name":    _clean_name(_find(r"name.*?(?:employer|deductor)\s*[:\-]?\s*([A-Za-z\s&\.\/]{5,80})", t)),
            "employee_address": _find(r"address.*?(?:employee|deductee)\s*[:\-]?\s*(.{10,100}?)(?:\n\n|pan)", t, flags=re.IGNORECASE | re.DOTALL),
            "employer_address": _find(r"address.*?(?:employer|deductor)\s*[:\-]?\s*(.{10,100}?)(?:\n\n|pan|tan)", t, flags=re.IGNORECASE | re.DOTALL),
            "pan_employee":     _find(r"pan.*?(?:employee|deductee)\s*[:\-]?\s*([A-Z]{5}\d{4}[A-Z])", t),
            "pan_employer":     _find(r"tan.*?(?:employer|deductor)\s*[:\-]?\s*([\w\d]{10})", t),
            "assessment_year":  _find(r"assessment\s*year\s*[:\-]?\s*(\d{4}[-\/]\d{2,4})", t),
            "acknowledgement_no": _find(r"acknowledgement\s*(?:no|number)\s*[:\-]?\s*(\d{10,})", t),
            "certificate_no":   _find(r"certificate\s*(?:no|number)\s*[:\-]?\s*([\w\d]+)", t),
            "quarter":          _find(r"quarter\s*[:\-]?\s*(Q[1-4]|[1-4](?:st|nd|rd|th)?)", t, flags=re.IGNORECASE),

            # Income
            "gross_salary":     _money(r"gross\s*salary\s*[:\-₹]?\s*([\d,\.]+)", t),
            "hra_received":     _money(r"hra\s*received\s*[:\-₹]?\s*([\d,\.]+)", t),
            "standard_deduction":_money(r"standard\s*deduction\s*[:\-₹]?\s*([\d,\.]+)", t),
            "gross_total_income":_money(r"gross\s*total\s*income\s*[:\-₹]?\s*([\d,\.]+)", t),
            "net_taxable_income":_money(r"(?:net\s*)?taxable\s*income\s*[:\-₹]?\s*([\d,\.]+)", t),

            # Tax
            "total_tax_payable": _money(r"total\s*tax\s*payable\s*[:\-₹]?\s*([\d,\.]+)", t),
            "total_tds":        _money(r"(?:total|amount\s*of).*?tds\s*[:\-₹]?\s*([\d,\.]+)", t),
            "tax_deposited":    _money(r"tax\s*deposited\s*[:\-₹]?\s*([\d,\.]+)", t),

            # Deductions u/s 80
            "deduction_80c":    _money(r"(?:section\s*)?80c\s*[:\-₹]?\s*([\d,\.]+)", t),
            "deduction_80d":    _money(r"(?:section\s*)?80d\s*[:\-₹]?\s*([\d,\.]+)", t),
            "total_deductions": _money(r"total\s*deductions?\s*[:\-₹]?\s*([\d,\.]+)", t),
        }


class UtilityBillExtractor:
    @staticmethod
    def extract(text: str) -> dict:
        t = text
        return {
            "customer_name":    _clean_name(_find(r"(?:john|name|customer|bill\s*to)\s*[:\-]?\s*([A-Z][A-Za-z\s\.]{3,40})", t)),
            "address":          _find(r"(\d+\s+[A-Za-z\s]+(?:street|st|road|rd|avenue|ave|lane|ln|nagar|marg)[^,\n]*)", t, flags=re.IGNORECASE),
            "city_state_zip":   _find(r"([A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5})", t),
            "account_number":   _find(r"(?:gas\s*south|account|a\/c)\s*(?:number|no|#)?\s*[:\-]?\s*(\d{7,15})", t),
            "rate_plan":        _find(r"rate\s*plan\s*[:\-]?\s*(\w+)", t),
            "bill_date":        _date(r"bill\s*date\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})", t),
            "due_date":         _date(r"(?:due\s*date|pay\s*by)\s*[:\-]?\s*(\w+\s+\d{1,2},?\s*\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})", t),
            "previous_balance": _money(r"previous\s*balance\s*[:\$\-]?\s*([\d,\.]+)", t),
            "payment_received": _money(r"payment(?:s?\s*received)?\s*[:\$\-]?\s*\(?([\d,\.]+)\)?", t),
            "current_charges":  _money(r"current\s*charges?\s*[:\$\-]?\s*([\d,\.]+)", t),
            "amount_due":       _money(r"(?:total\s*)?amount\s*due\s*[:\$\-]?\s*([\d,\.]+)", t),
            "gas_charges":      _money(r"gas\s*charges?\s*[:\$\-]?\s*([\d,\.]+)", t),
            "service_fee":      _money(r"(?:customer\s*)?service\s*fee\s*[:\$\-]?\s*([\d,\.]+)", t),
            "taxes":            _money(r"taxes?\s*[:\$\-]?\s*([\d,\.]+)", t),
            "meter_start":      _find(r"(?:beginning|start)\s*(?:read)?\s*[:\-]?\s*(\d+)", t),
            "meter_end":        _find(r"(?:ending|end)\s*(?:read)?\s*[:\-]?\s*(\d+)", t),
            "units_consumed":   _find(r"(\d+)\s*(?:therms?|units?|kwh)", t),
            "utility_provider": _find(r"^([A-Z][A-Za-z\s&\.]{3,30}?)(?:\n|gas|electric|water|energy)", t),
            "customer_service": _find(r"customer\s*service\s*[:\-]?\s*([\d\-\s\(\)]+)", t),
        }


class CancelledChequeExtractor:
    @staticmethod
    def extract(text: str) -> dict:
        t = text
        return {
            "bank_name":       _find(r"(axis\s*bank|punjab\s*national\s*bank|hdfc\s*bank|state\s*bank|icici\s*bank|canara\s*bank|bank\s*of\s*baroda|kotak|yes\s*bank|union\s*bank)", t, flags=re.IGNORECASE),
            "account_number":  _find(r"a/c\s*no[\.:\s]*([\d\s]{9,20})", t),
            "account_type":    _find(r"(savings?\s*a/c|savings?\s*account|current\s*account|salary\s*account)", t, flags=re.IGNORECASE),
            "ifsc_code":       _find(r"(?:ifsc|ifs\s*code)\s*[:\-]?\s*([A-Z]{4}0[A-Z0-9]{6})", t),
            "micr_code":       _find(r"(\d{9})", t),
            "cheque_number":   _find(r"(?:cheque\s*no|chq\s*no)\s*[:\-]?\s*(\d{6})", t),
            "branch":          _find(r"(?:branch|location)\s*[:\-]?\s*([A-Za-z\s\(\)]{3,40})", t),
            "payee_name":      _clean_name(_find(r"pay\s*[:\-]?\s*([A-Z][A-Za-z\s]{3,40})", t)),
            "account_holder":  _clean_name(_find(r"(?:name|account\s*holder)\s*[:\-]?\s*([A-Z][A-Za-z\s]{3,40})", t)),
            "bank_address":    _find(r"([A-Za-z\s\[\]]+,\s*[A-Za-z\s]+[-\s]\d{6})", t),
        }


class ITRExtractor:
    @staticmethod
    def extract(text: str) -> dict:
        t = text
        return {
            "applicant_name":    _clean_name(_find(r"name\s*[:\-]?\s*([A-Z][A-Za-z\s]{3,40})", t)),
            "pan_number":        _pan(t),
            "assessment_year":   _find(r"assessment\s*year\s*[:\-]?\s*(\d{4}[-\/]\d{2,4})", t),
            "acknowledgement_no":_find(r"acknowledgement\s*(?:no|number)\s*[:\-]?\s*(\d{10,15})", t),
            "filing_date":       _date(r"(?:date\s*of\s*filing|e-filing\s*date)\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", t),
            "itr_form":          _find(r"(itr[-\s]*[1-7v])", t, flags=re.IGNORECASE),
            "gross_total_income":_money(r"gross\s*total\s*income\s*[:\-₹]?\s*([\d,\.]+)", t),
            "total_income":      _money(r"(?:^|\s)total\s*income\s*[:\-₹]?\s*([\d,\.]+)", t),
            "tax_payable":       _money(r"tax\s*payable\s*[:\-₹]?\s*([\d,\.]+)", t),
            "refund_due":        _money(r"refund\s*(?:due|amount)\s*[:\-₹]?\s*([\d,\.]+)", t),
            "tds_claimed":       _money(r"tds\s*(?:claimed|credit)\s*[:\-₹]?\s*([\d,\.]+)", t),
        }


class PANCardExtractor:
    @staticmethod
    def extract(text: str) -> dict:
        t = text
        return {
            "name":        _clean_name(_find(r"^([A-Z][A-Z\s]{3,30})$", t, flags=re.MULTILINE)),
            "pan_number":  _pan(t),
            "dob":         _date(r"(\d{2}/\d{2}/\d{4})", t),
            "father_name": _clean_name(_find(r"father.?s?\s*name\s*[:\-]?\s*([A-Z][A-Za-z\s]{3,40})", t)),
        }


# ── Dispatcher ─────────────────────────────────────────────────────────────────

_EXTRACTORS = {
    "salary_slip":       SalarySlipExtractor.extract,
    "bank_statement":    BankStatementExtractor.extract,
    "form_16":           Form16Extractor.extract,
    "utility_bill":      UtilityBillExtractor.extract,
    "cancelled_cheque":  CancelledChequeExtractor.extract,
    "income_tax_return": ITRExtractor.extract,
    "pan_card":          PANCardExtractor.extract,
}


def extract_fields(doc_type: str, text: str) -> dict:
    """
    Dispatch extraction to the right extractor class.
    Returns a dict of field_name -> value (None if not found).
    """
    fn = _EXTRACTORS.get(doc_type)
    if not fn:
        logger.warning(f"No extractor for doc_type: {doc_type}")
        return {}
    try:
        raw = fn(text)
        # Strip None values to keep response clean (but include all keys)
        return {k: v for k, v in raw.items()}
    except Exception as e:
        logger.error(f"Extractor failed for {doc_type}: {e}")
        return {}


def get_key_fields(doc_type: str, fields: dict) -> dict:
    """Return only the most important fields for a quick summary."""
    KEY_FIELDS = {
        "salary_slip":       ["employee_name", "net_salary", "gross_earnings", "month_year", "days_present"],
        "bank_statement":    ["account_holder", "account_number", "bank_name", "opening_balance", "closing_balance"],
        "form_16":           ["employee_name", "employer_name", "assessment_year", "gross_salary", "total_tds"],
        "utility_bill":      ["customer_name", "address", "amount_due", "due_date", "bill_date"],
        "cancelled_cheque":  ["bank_name", "account_number", "ifsc_code", "account_type"],
        "income_tax_return": ["applicant_name", "pan_number", "assessment_year", "gross_total_income"],
        "pan_card":          ["name", "pan_number", "dob"],
    }
    keys = KEY_FIELDS.get(doc_type, list(fields.keys())[:5])
    return {k: fields.get(k) for k in keys}
