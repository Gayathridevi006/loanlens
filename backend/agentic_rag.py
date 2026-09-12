"""Auditable, local-first agentic RAG orchestration for loan applications.

The module deliberately keeps model calls behind deterministic tools. Applicant
data never leaves the service, every conclusion carries evidence identifiers,
and a verifier can force uncertain recommendations to human review.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .rag_evaluation import retrieve, tokens


AMOUNT_KEYS = {
    "income", "annual_income", "gross_total_income", "gross_salary",
    "net_salary", "gross_earnings", "monthly_income", "total_income", "loan_amount", "amount",
}
IDENTITY_ALIASES = {
    "name": ("applicant_name", "name", "customer_name", "borrower_name", "employee_name", "account_holder"),
    "pan": ("pan", "pan_number", "pan_no", "pan_employee"),
    "phone": ("phone", "phone_number", "mobile", "mobile_number", "applicant_phone"),
}
INTENT_TERMS = {
    "fraud": "fraud anomaly mismatch duplicate forged tampered identity PAN income employer document",
    "income": "income salary earnings credits ITR tax annual monthly bank",
    "eligibility": "eligibility loan amount EMI credit score debt income employment policy",
    "documents": "document submitted missing statement salary slip ITR PAN verification",
    "general": "loan application evidence profile decision risk",
}
INTENT_KEYWORDS = {
    "fraud": ("fraud", "anomaly", "mismatch", "duplicate", "forged", "tampered", "fake"),
    "income": ("income", "salary", "earnings", "itr", "tax", "bank credit"),
    "eligibility": ("eligibility", "eligible", "emi", "credit score", "dti", "loan amount"),
    "documents": ("document", "submitted", "missing", "statement", "proof"),
}
STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "was", "were",
    "are", "has", "have", "not", "but", "into", "than", "its", "per",
}
SUSPICIOUS_TERMS = {
    "forged": 36, "fabricated": 36, "tampered": 32, "fake document": 36,
    "altered statement": 30, "identity mismatch": 28, "unverifiable": 18,
    "cash only": 10, "suspicious": 12,
}
PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions", "ignore all instructions", "system prompt",
    "approve regardless", "bypass policy", "do not report fraud", "override decision",
)


@dataclass
class EvidenceChunk:
    id: str
    source: str
    document_type: str
    text: str
    fields: dict[str, Any] = field(default_factory=dict)
    page: int | None = None
    section: str = ""
    score: float = 0.0

    def public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FraudSignal:
    code: str
    severity: str
    points: float
    description: str
    evidence_ids: list[str]


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "document"


def _safe_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _display_value(value: Any) -> str:
    if value is None or value == "":
        return "not provided"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value).strip()


def _document_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value for key, value in data.items()
        if key not in {"documents", "comments", "statement", "text", "content"}
        and _safe_scalar(value) and value not in (None, "")
    }


def _split_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return []
    chunks, start = [], 0
    while start < len(compact):
        end = min(len(compact), start + size)
        if end < len(compact):
            boundary = compact.rfind(" ", start, end)
            if boundary > start + size // 2:
                end = boundary
        chunks.append(compact[start:end].strip())
        if end >= len(compact):
            break
        start = max(start + 1, end - overlap)
    return chunks


def build_evidence(record: dict[str, Any]) -> list[EvidenceChunk]:
    """Turn structured fields and document text into source-addressable chunks."""
    chunks: list[EvidenceChunk] = []

    def add_document(data: dict[str, Any], source: str, ordinal: int) -> None:
        fields = _document_fields(data)
        doc_type = str(data.get("document_type") or data.get("doc_type") or "application")
        prefix = f"{_slug(source)}-{ordinal}"
        structured = "; ".join(f"{key}: {_display_value(value)}" for key, value in sorted(fields.items()))
        if structured:
            chunks.append(EvidenceChunk(
                f"{prefix}-fields", source, doc_type, structured, fields,
                int(data["page"]) if str(data.get("page", "")).isdigit() else None,
                "extracted_fields",
            ))
        narrative = "\n".join(
            str(data.get(key) or "") for key in ("comments", "statement", "text", "content")
        )
        for index, part in enumerate(_split_text(narrative), 1):
            chunks.append(EvidenceChunk(
                f"{prefix}-text-{index}", source, doc_type, part, fields,
                int(data["page"]) if str(data.get("page", "")).isdigit() else None,
                "document_text",
            ))

    root = {key: value for key, value in record.items() if key != "documents"}
    add_document(root, "application-profile", 1)
    for index, item in enumerate(record.get("documents") or [], 1):
        if not isinstance(item, dict):
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else item
        source = str(item.get("filename") or data.get("source_file") or f"document-{index}")
        add_document(data, source, index)
    if not chunks:
        chunks.append(EvidenceChunk("application-profile-1-fields", "application-profile", "application", "No application fields were supplied."))
    return chunks


def plan_query(question: str, top_k: int = 5) -> dict[str, Any]:
    lowered = (question or "").lower()
    scores = {
        intent: sum(term in lowered for term in keywords)
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    intent = max(scores, key=scores.get) if scores and max(scores.values()) else "general"
    tools = ["hybrid_retriever"]
    if intent in {"fraud", "general"}:
        tools.append("fraud_investigator")
    if intent in {"eligibility", "general", "income"}:
        tools.append("credit_risk_scorecard")
    tools.extend(["grounded_answer_writer", "evidence_verifier"])
    return {
        "intent": intent,
        "query": question,
        "expanded_query": f"{question} {INTENT_TERMS[intent]}",
        "top_k": max(1, min(top_k, 12)),
        "tools": tools,
    }


def hybrid_retrieve(
    plan: dict[str, Any],
    evidence: list[EvidenceChunk],
    semantic_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Combine BM25 content rank with structured-field and document-type boosts."""
    corpus = [{"id": chunk.id, "text": chunk.text} for chunk in evidence]
    lexical_results = retrieve(plan["expanded_query"], corpus, len(corpus))
    ranked = {item["id"]: item["score"] for item in lexical_results}
    lexical_rank = {item["id"]: rank for rank, item in enumerate(lexical_results, 1)}
    semantic_rank = {item["id"]: int(item["semantic_rank"]) for item in semantic_results or []}
    query_terms = set(tokens(plan["query"]))
    results = []
    for chunk in evidence:
        field_terms = set(tokens(" ".join(chunk.fields)))
        type_terms = set(tokens(chunk.document_type.replace("_", " ")))
        structured_boost = 0.45 * len(query_terms & field_terms)
        type_boost = 0.35 * len(query_terms & type_terms)
        reciprocal_rank = 1 / (60 + lexical_rank.get(chunk.id, len(evidence) + 1))
        if chunk.id in semantic_rank:
            reciprocal_rank += 1 / (60 + semantic_rank[chunk.id])
        score = round(float(ranked.get(chunk.id, 0)) + structured_boost + type_boost + reciprocal_rank * 20, 6)
        results.append(chunk.public() | {
            "score": score,
            "lexical_rank": lexical_rank.get(chunk.id),
            "semantic_rank": semantic_rank.get(chunk.id),
        })
    results.sort(key=lambda item: (item["score"], item["id"]), reverse=True)
    return results[: plan["top_k"]]


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        cleaned = re.sub(r"[^0-9.\-]", "", str(value).replace(",", ""))
        return float(cleaned) if cleaned else None
    except (TypeError, ValueError):
        return None


def _observations(evidence: list[EvidenceChunk], aliases: tuple[str, ...]) -> list[tuple[str, str]]:
    found, seen = [], set()
    for chunk in evidence:
        for key in aliases:
            value = chunk.fields.get(key)
            if value in (None, ""):
                continue
            normalized = re.sub(r"\s+", " ", str(value)).strip()
            marker = (chunk.source, key, normalized.lower())
            if marker not in seen:
                found.append((chunk.id, normalized))
                seen.add(marker)
    return found


def _identity_conflicts(identity_type: str, observations: list[tuple[str, str]]) -> bool:
    if identity_type == "name":
        names = [set(term for term in tokens(value) if len(term) > 1) for _, value in observations]
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                if left and right and not (left <= right or right <= left) and len(left & right) / len(left | right) < 0.6:
                    return True
        return False
    if identity_type == "phone":
        normalized = {re.sub(r"\D", "", value)[-10:] for _, value in observations}
    else:
        normalized = {re.sub(r"[^a-z0-9]", "", value.lower()) for _, value in observations}
    return len({value for value in normalized if value}) > 1


def investigate_fraud(record: dict[str, Any], evidence: list[EvidenceChunk], base_score: float = 0) -> dict[str, Any]:
    """Detect cross-document inconsistencies and suspicious application patterns."""
    signals: list[FraudSignal] = []

    for identity_type, aliases in IDENTITY_ALIASES.items():
        observations = _observations(evidence, aliases)
        if _identity_conflicts(identity_type, observations):
            signals.append(FraudSignal(
                f"IDENTITY_{identity_type.upper()}_MISMATCH", "HIGH", 30,
                f"Conflicting {identity_type} values appear across submitted evidence.",
                sorted({item[0] for item in observations}),
            ))

    income_values: list[tuple[str, float]] = []
    for chunk in evidence:
        for key, value in chunk.fields.items():
            if key.lower() not in AMOUNT_KEYS or "loan" in key.lower() or key.lower() == "amount":
                continue
            amount = _number(value)
            if amount is None or amount <= 0:
                continue
            if "monthly" in key.lower() or key.lower() in {"net_salary", "gross_earnings"}:
                amount *= 12
            income_values.append((chunk.id, amount))
    if len(income_values) > 1:
        smallest, largest = min(v for _, v in income_values), max(v for _, v in income_values)
        if smallest and largest / smallest >= 1.5:
            ids = sorted({item[0] for item in income_values})
            signals.append(FraudSignal(
                "INCOME_MISMATCH", "HIGH", 28,
                f"Income evidence differs by {((largest / smallest) - 1) * 100:.0f}% across documents.", ids,
            ))

    documents = [chunk for chunk in evidence if chunk.source != "application-profile" and chunk.fields]
    fingerprints: dict[str, list[str]] = {}
    for chunk in documents:
        canonical = json.dumps(chunk.fields, sort_keys=True, default=str).lower()
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        fingerprints.setdefault(digest, []).append(chunk.id)
    duplicates = [ids for ids in fingerprints.values() if len({item.rsplit("-", 1)[0] for item in ids}) > 1]
    if duplicates:
        signals.append(FraudSignal(
            "DUPLICATE_DOCUMENT", "MEDIUM", 18,
            "Identical structured evidence appears in more than one submitted document.",
            sorted({item for group in duplicates for item in group}),
        ))

    combined_text = " ".join(chunk.text.lower() for chunk in evidence)
    injection_hits = [pattern for pattern in PROMPT_INJECTION_PATTERNS if pattern in combined_text]
    if injection_hits:
        ids = [chunk.id for chunk in evidence if any(pattern in chunk.text.lower() for pattern in injection_hits)]
        signals.append(FraudSignal(
            "PROMPT_INJECTION_CONTENT", "HIGH", 32,
            "A submitted document contains instruction-like text that the agent ignored as untrusted content.", ids,
        ))
    for phrase, points in SUSPICIOUS_TERMS.items():
        if phrase in combined_text:
            ids = [chunk.id for chunk in evidence if phrase in chunk.text.lower()]
            signals.append(FraudSignal(
                "SUSPICIOUS_LANGUAGE", "HIGH" if points >= 28 else "MEDIUM", points,
                f"Submitted evidence contains the risk phrase “{phrase}”.", ids,
            ))
            break

    income = _number(record.get("income") or record.get("annual_income")) or 0
    amount = _number(record.get("loan_amount") or record.get("amount")) or 0
    profile_id = next((item.id for item in evidence if item.source == "application-profile"), evidence[0].id)
    if income > 0 and amount > max(income * 8, 1_000_000):
        signals.append(FraudSignal(
            "EXTREME_LOAN_TO_INCOME", "MEDIUM", 18,
            f"Requested loan is {amount / income:.1f}× declared annual income.", [profile_id],
        ))
    if record.get("duplicate") is True:
        signals.append(FraudSignal(
            "DUPLICATE_APPLICATION", "HIGH", 28,
            "The intake record is marked as a possible duplicate application.", [profile_id],
        ))
    years = _number(record.get("employment_years") or record.get("experience")) or 0
    if years > 0 and not record.get("employer") and not record.get("employer_name"):
        signals.append(FraudSignal(
            "EMPLOYER_UNVERIFIED", "MEDIUM", 14,
            "Employment duration is declared but employer evidence is absent.", [profile_id],
        ))
    pan_values = _observations(evidence, IDENTITY_ALIASES["pan"])
    invalid_pan = [(item_id, value) for item_id, value in pan_values if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", value.upper().replace(" ", ""))]
    if invalid_pan:
        signals.append(FraudSignal(
            "INVALID_PAN_FORMAT", "MEDIUM", 18,
            "A supplied PAN does not match the expected Indian PAN format.",
            sorted({item[0] for item in invalid_pan}),
        ))

    investigation_score = min(100.0, 5.0 + sum(signal.points for signal in signals))
    final_score = round(max(float(base_score), investigation_score), 1)
    risk_level = "CRITICAL" if final_score >= 75 else "HIGH" if final_score >= 50 else "MEDIUM" if final_score >= 25 else "LOW"
    return {
        "score": final_score,
        "risk_level": risk_level,
        "confidence": round(min(0.98, 0.42 + len(evidence) * 0.07 + len(signals) * 0.04), 2),
        "signals": [asdict(signal) for signal in signals],
        "checks_performed": [
            "cross-document identity consistency", "income consistency", "duplicate document fingerprinting",
            "suspicious-language screening", "prompt-injection defence", "loan-to-income anomaly", "employer evidence", "PAN format",
        ],
    }


def _tool_evidence(base_analysis: dict[str, Any], fraud: dict[str, Any], decision: dict[str, Any]) -> list[dict[str, Any]]:
    risk_id, fraud_id, decision_id = "tool-credit-risk", "tool-fraud-investigation", "tool-policy-decision"
    signal_summary = " ".join(signal["description"] for signal in fraud["signals"]) or "No material inconsistency was detected."
    return [
        {
            "id": risk_id, "source": "credit-risk-scorecard", "document_type": "tool_result",
            "text": (
                f"Credit risk score is {base_analysis['risk_score']:.1f} out of 100. "
                f"Credit score is {base_analysis['credit_score']}. Debt-to-income ratio is {base_analysis['dti']:.1f} percent."
            ), "fields": {}, "score": 1.0,
        },
        {
            "id": fraud_id, "source": "fraud-investigator", "document_type": "tool_result",
            "text": (
                f"Fraud risk score is {fraud['score']:.1f} out of 100 and risk level is {fraud['risk_level']}. "
                f"Detected {len(fraud['signals'])} fraud signals. {signal_summary}"
            ), "fields": {}, "score": 1.0,
        },
        {
            "id": decision_id, "source": "policy-decision", "document_type": "tool_result",
            "text": (
                f"Recommendation is {decision['recommendation']}. "
                f"Human loan officer review is {'required' if decision['human_review_required'] else 'not required'}."
            ), "fields": {}, "score": 1.0,
        },
    ]


def _decision(base_analysis: dict[str, Any], fraud: dict[str, Any], document_assessment: dict[str, Any]) -> dict[str, Any]:
    risk = float(base_analysis["risk_score"])
    fraud_score = float(fraud["score"])
    if fraud_score >= 75 or risk >= 70:
        recommendation = "REJECT"
    elif fraud_score >= 40 or risk >= 40 or not document_assessment["complete"]:
        recommendation = "REVIEW"
    else:
        recommendation = "APPROVE"
    return {
        "recommendation": recommendation,
        "risk_score": risk,
        "fraud_score": fraud_score,
        "human_review_required": recommendation == "REVIEW" or fraud_score >= 40,
        "adverse_action_notice_required": recommendation == "REJECT",
        "decision_authority": "deterministic-policy-engine",
        "agent_role": "advisory-only",
        "policy_note": "Decision support only; a loan officer must apply the lender's approved policy and fairness controls.",
    }


def _excerpt(text: str, limit: int = 190) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def compose_answer(plan: dict[str, Any], retrieved: list[dict[str, Any]], fraud: dict[str, Any], decision: dict[str, Any], tool_evidence: list[dict[str, Any]], policy_evidence: list[dict[str, Any]]) -> str:
    risk_ref, fraud_ref, decision_ref = (item["id"] for item in tool_evidence)
    lines = [
        f"Recommendation: {decision['recommendation']} [{decision_ref}]. Credit risk is {decision['risk_score']:.1f}/100 [{risk_ref}] and fraud risk is {decision['fraud_score']:.1f}/100 ({fraud['risk_level']}) [{fraud_ref}]."
    ]
    if plan["intent"] == "fraud" or fraud["signals"]:
        if fraud["signals"]:
            for signal in fraud["signals"][:4]:
                citations = f"[{fraud_ref}] " + " ".join(f"[{item}]" for item in signal["evidence_ids"][:2])
                lines.append(f"Fraud check: {signal['description']} {citations}")
        else:
            lines.append(f"Fraud check: no material inconsistency was found by the configured checks [{fraud_ref}].")
    if plan["intent"] in {"income", "documents", "general"} and retrieved:
        for item in retrieved[:3]:
            lines.append(f"Evidence: {_excerpt(item['text'])} [{item['id']}].")
    if plan["intent"] in {"eligibility", "documents", "general"} and policy_evidence:
        policy = policy_evidence[0]
        lines.append(f"Policy: {_excerpt(policy['text'])} [{policy['id']}].")
    if decision["human_review_required"]:
        lines.append(f"Next action: route this application to a loan officer for document-level review [{decision_ref}].")
    return "\n".join(lines)


def verify_grounding(answer: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Require valid citations and lexical support for each factual answer line."""
    by_id = {item["id"]: item for item in evidence}
    citation_ids = re.findall(r"\[([^\[\]]+)\]", answer)
    invalid = sorted({citation for citation in citation_ids if citation not in by_id})
    factual_lines = [line.strip() for line in answer.splitlines() if line.strip()]
    uncited = [line for line in factual_lines if not re.search(r"\[[^\[\]]+\]", line)]
    supported, considered = 0, 0
    for line in factual_lines:
        line_citations = [item for item in re.findall(r"\[([^\[\]]+)\]", line) if item in by_id]
        if not line_citations:
            continue
        claim_terms = {term for term in tokens(re.sub(r"\[[^\[\]]+\]", "", line)) if len(term) > 2 and term not in STOP_WORDS}
        source_terms = set(tokens(" ".join(by_id[item]["text"] for item in line_citations)))
        considered += len(claim_terms)
        supported += len(claim_terms & source_terms)
    groundedness = supported / considered if considered else 1.0
    citation_coverage = (len(factual_lines) - len(uncited)) / len(factual_lines) if factual_lines else 1.0
    return {
        "verified": not invalid and not uncited and groundedness >= 0.45,
        "groundedness": round(groundedness, 4),
        "citation_coverage": round(citation_coverage, 4),
        "citations": list(dict.fromkeys(citation_ids)),
        "invalid_citations": invalid,
        "uncited_claims": uncited,
    }


def run_agentic_assessment(
    record: dict[str, Any],
    base_analysis: dict[str, Any],
    question: str | None = None,
    top_k: int = 5,
    semantic_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute the complete multi-tool RAG loop and return an auditable report."""
    query = question or "Assess fraud, credit risk, eligibility, income consistency, and document evidence."
    trace: list[dict[str, Any]] = []
    plan = plan_query(query, top_k)
    trace.append({"agent": "planner", "status": "completed", "output": {"intent": plan["intent"], "tools": plan["tools"]}})
    evidence = build_evidence(record)
    retrieved = hybrid_retrieve(plan, evidence, semantic_results)
    trace.append({"agent": "retriever", "status": "completed", "output": {
        "corpus_chunks": len(evidence), "retrieved_chunks": len(retrieved),
        "semantic_candidates": len(semantic_results or []), "fusion": "reciprocal-rank + structured boosts",
    }})
    from .policy_engine import adverse_action_reasons, assess_documents, retrieve_policies

    document_assessment = assess_documents(record, evidence)
    trace.append({"agent": "document_specialist", "status": "completed", "output": {
        "missing": document_assessment["missing_categories"], "expired": len(document_assessment["expired_documents"]),
    }})
    fraud = investigate_fraud(record, evidence, float(base_analysis.get("fraud_score", 0)))
    from .local_models import fraud_anomaly_model
    anomaly = fraud_anomaly_model.predict(record)
    fraud["anomaly_model"] = asdict(anomaly)
    trace.append({"agent": "fraud_investigator", "status": "completed", "output": {
        "score": fraud["score"], "signals": len(fraud["signals"]),
        "isolation_forest_available": anomaly.available, "isolation_forest_version": anomaly.model_version,
    }})
    trace.append({"agent": "credit_risk", "status": "completed", "output": {"score": base_analysis["risk_score"]}})
    decision = _decision(base_analysis, fraud, document_assessment)
    decision["adverse_action_reasons"] = adverse_action_reasons(base_analysis["risk_score"], fraud, document_assessment)
    decision["model_versions"] = {
        "credit_scorecard": "scorecard-2026.09",
        "fraud_scorecard": "scorecard-2026.09",
        "fraud_isolation_forest": anomaly.model_version,
        "policy": document_assessment["policy_version"],
    }
    policy_evidence = retrieve_policies(query, min(3, top_k))
    trace.append({"agent": "compliance", "status": "completed", "output": {
        "policy_version": document_assessment["policy_version"], "policies_retrieved": len(policy_evidence),
    }})
    tool_evidence = _tool_evidence(base_analysis, fraud, decision)
    answer = compose_answer(plan, retrieved, fraud, decision, tool_evidence, policy_evidence)
    trace.append({"agent": "answer_writer", "status": "completed", "output": {"answer_lines": len(answer.splitlines())}})
    verification = verify_grounding(answer, retrieved + tool_evidence + policy_evidence + [item.public() for item in evidence])
    if not verification["verified"] and decision["recommendation"] == "APPROVE":
        decision["recommendation"] = "REVIEW"
        decision["human_review_required"] = True
        decision["guardrail_reason"] = "Grounding verification did not meet the approval threshold."
    trace.append({"agent": "verifier", "status": "completed", "output": verification})
    return {
        "query": query,
        "plan": plan,
        "answer": answer,
        "decision": decision,
        "fraud_assessment": fraud,
        "document_assessment": document_assessment,
        "retrieved_evidence": retrieved,
        "policy_evidence": policy_evidence,
        "verification": verification,
        "trace": trace,
    }
