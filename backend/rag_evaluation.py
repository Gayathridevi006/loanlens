"""Deterministic retrieval backtesting and evidence-grounding verification."""
from __future__ import annotations

import math
import re
import time
from collections import Counter

TOKEN = re.compile(r"[a-z0-9]+", re.I)


def tokens(text: str) -> list[str]:
    return TOKEN.findall((text or "").lower())


def retrieve(query: str, corpus: list[dict], top_k: int = 3) -> list[dict]:
    """Rank evidence chunks with a compact BM25 implementation."""
    docs = [{**doc, "_tokens": tokens(str(doc.get("text", "")))} for doc in corpus]
    if not docs:
        return []
    query_tokens = tokens(query)
    avg_len = sum(len(doc["_tokens"]) for doc in docs) / len(docs) or 1
    document_frequency = Counter()
    for term in set(query_tokens):
        document_frequency[term] = sum(term in doc["_tokens"] for doc in docs)
    ranked = []
    for doc in docs:
        frequencies = Counter(doc["_tokens"])
        score = 0.0
        for term in query_tokens:
            df = document_frequency[term]
            idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
            tf = frequencies[term]
            score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * len(doc["_tokens"]) / avg_len)) if tf else 0
        ranked.append({k: v for k, v in doc.items() if k != "_tokens"} | {"score": round(score, 6)})
    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:top_k]


def verify_answer(answer: str, evidence: list[dict], required_terms: list[str] | None = None) -> dict:
    """Check lexical support and required facts without allowing unsupported confidence."""
    answer_terms = set(tokens(answer))
    evidence_terms = set(tokens(" ".join(str(item.get("text", "")) for item in evidence)))
    informative = {t for t in answer_terms if len(t) > 2}
    supported = informative & evidence_terms
    coverage = len(supported) / len(informative) if informative else 1.0
    missing_required = [term for term in required_terms or [] if term.lower() not in answer.lower()]
    evidence_ids = {str(item.get("id", "")) for item in evidence}
    citations = re.findall(r"\[([^\[\]]+)\]", answer)
    valid_citations = [citation for citation in citations if citation in evidence_ids]
    return {
        "groundedness": round(coverage, 4),
        "supported_terms": len(supported),
        "answer_terms": len(informative),
        "missing_required_terms": missing_required,
        "citation_accuracy": round(len(valid_citations) / len(citations), 4) if citations else None,
        "invalid_citations": sorted(set(citations) - evidence_ids),
        "verified": coverage >= 0.6 and not missing_required,
    }


def run_backtest(cases: list[dict], top_k: int = 3) -> dict:
    results, hits, recalls, reciprocal_ranks, groundedness, citation_scores, contradictions, latencies, decision_hits = [], 0, [], [], [], [], [], [], []
    for case in cases:
        started = time.perf_counter()
        retrieved = retrieve(case["query"], case.get("corpus", []), top_k)
        latencies.append((time.perf_counter() - started) * 1000)
        ids = [str(item.get("id", "")) for item in retrieved]
        expected = set(map(str, case.get("expected_document_ids", [])))
        ranks = [index + 1 for index, value in enumerate(ids) if value in expected]
        hit = bool(ranks) if expected else True
        hits += int(hit)
        recalls.append(len(expected & set(ids)) / len(expected) if expected else 1.0)
        reciprocal_ranks.append(1 / min(ranks) if ranks else 0)
        verification = verify_answer(
            case.get("generated_answer", ""), retrieved, case.get("expected_answer_terms", [])
        )
        groundedness.append(verification["groundedness"])
        if verification["citation_accuracy"] is not None:
            citation_scores.append(verification["citation_accuracy"])
        contradiction_terms = case.get("expected_not_terms", [])
        contradiction = any(term.lower() in case.get("generated_answer", "").lower() for term in contradiction_terms)
        contradictions.append(contradiction)
        if case.get("expected_decision") is not None:
            decision_hits.append(case.get("expected_decision") == case.get("actual_decision"))
        results.append({
            "case_id": case["case_id"], "retrieved_ids": ids, "retrieval_hit": hit,
            "recall_at_k": recalls[-1], "reciprocal_rank": reciprocal_ranks[-1],
            "contradiction": contradiction, "latency_ms": round(latencies[-1], 3), "verification": verification,
        })
    count = len(cases)
    metrics = {
        f"hit_rate_at_{top_k}": round(hits / count, 4),
        f"recall_at_{top_k}": round(sum(recalls) / count, 4),
        "mean_reciprocal_rank": round(sum(reciprocal_ranks) / count, 4),
        "mean_groundedness": round(sum(groundedness) / count, 4),
        "verification_pass_rate": round(sum(r["verification"]["verified"] for r in results) / count, 4),
        "citation_accuracy": round(sum(citation_scores) / len(citation_scores), 4) if citation_scores else None,
        "hallucination_rate": round(sum(1 - value for value in groundedness) / count, 4),
        "contradiction_rate": round(sum(contradictions) / count, 4),
        "mean_retrieval_latency_ms": round(sum(latencies) / count, 3),
        "decision_error_rate": round(1 - sum(decision_hits) / len(decision_hits), 4) if decision_hits else None,
        "decision_accuracy": round(sum(decision_hits) / len(decision_hits), 4) if decision_hits else None,
    }
    return {"dataset_size": count, "top_k": top_k, "metrics": metrics, "results": results}
