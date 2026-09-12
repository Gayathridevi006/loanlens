from backend.rag_evaluation import retrieve, run_backtest, verify_answer


CORPUS = [
    {"id": "bank-1", "text": "Closing bank balance is INR 125000 and salary credits are regular."},
    {"id": "itr-1", "text": "Gross total income for assessment year 2025-26 is INR 900000."},
]


def test_retrieval_ranks_relevant_evidence_first():
    assert retrieve("What is the closing bank balance?", CORPUS, 1)[0]["id"] == "bank-1"


def test_verification_rejects_unsupported_answer():
    result = verify_answer("The applicant owns three houses and earns 5 crore", [CORPUS[0]])
    assert not result["verified"]
    assert result["groundedness"] < 0.6


def test_backtest_reports_retrieval_grounding_and_decision_metrics():
    report = run_backtest([{
        "case_id": "case-1", "query": "gross total income", "corpus": CORPUS,
        "expected_document_ids": ["itr-1"], "expected_answer_terms": ["900000"],
        "generated_answer": "Gross total income is INR 900000",
        "expected_decision": "REVIEW", "actual_decision": "REVIEW",
    }], top_k=1)
    assert report["metrics"]["hit_rate_at_1"] == 1
    assert report["metrics"]["decision_accuracy"] == 1
    assert report["results"][0]["verification"]["verified"]

