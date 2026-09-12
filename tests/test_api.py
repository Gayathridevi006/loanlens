def create(client, name="Priya Sharma"):
    return client.post("/applications", json={
        "applicant_name": name, "income": 900000, "loan_amount": 500000,
        "credit_score": 760, "dti": 22, "employment_years": 5,
    })


def test_application_search_and_pagination(client):
    assert create(client).status_code == 201
    assert create(client, "Other Applicant").status_code == 201
    response = client.get("/applications", params={"q": "Priya", "page": 1, "page_size": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["applicant_name"] == "Priya Sharma"


def test_dashboard_months_are_scoped_to_latest_year(client):
    assert create(client).status_code == 201
    body = client.get("/dashboard").json()
    assert body["monthly_year"]
    assert sum(month["applications"] for month in body["monthly"]) == 1


def test_backtest_endpoint_persists_metrics(client):
    response = client.post("/evaluation/backtest", json={"name": "smoke", "top_k": 1, "cases": [{
        "case_id": "c1", "query": "salary", "corpus": [{"id": "d1", "text": "salary is 50000"}],
        "expected_document_ids": ["d1"], "expected_answer_terms": ["50000"],
        "generated_answer": "salary is 50000",
    }]})
    assert response.status_code == 201
    assert response.json()["metrics"]["hit_rate_at_1"] == 1
    assert len(client.get("/evaluation/runs").json()) == 1


def test_agent_analysis_and_query_are_persisted(client):
    created = create(client).json()
    analysis = client.post(f"/applications/{created['id']}/agent/analyze")
    assert analysis.status_code == 201
    assert analysis.json()["verification"]["verified"]
    assert analysis.json()["trace"][0]["agent"] == "planner"

    query = client.post(
        f"/applications/{created['id']}/agent/query",
        json={"question": "Are there fraud or identity mismatch signals?", "top_k": 3},
    )
    assert query.status_code == 201
    assert query.json()["plan"]["intent"] == "fraud"
    runs = client.get(f"/applications/{created['id']}/agent/runs").json()
    assert len(runs) == 2
    assert runs[0]["verification"]["citation_coverage"] == 1


def test_officer_override_and_governance_endpoints(client):
    created = create(client).json()
    override = client.post(f"/applications/{created['id']}/override", json={
        "new_status": "REJECT", "reason": "Verified employer records conflict with the submitted application.",
    })
    assert override.status_code == 201
    assert override.json()["previous_status"] == "REVIEW"
    assert client.get("/governance/models").status_code == 200
    assert client.get("/governance/drift").json()["sample_size"] == 1


def test_vector_backend_and_extended_evaluation_metrics(client):
    backend = client.get("/agent/capabilities").json()["vector_store"]
    assert backend["engine"] in {"pgvector", "local-cosine-fallback"}
    response = client.post("/evaluation/backtest", json={"name": "extended", "top_k": 1, "cases": [{
        "case_id": "c1", "query": "income", "corpus": [{"id": "d1", "text": "income is 50000"}],
        "expected_document_ids": ["d1"], "generated_answer": "income is 50000 [d1]",
    }]})
    metrics = response.json()["metrics"]
    assert metrics["recall_at_1"] == 1
    assert metrics["citation_accuracy"] == 1


def test_auth_can_be_enforced_without_blocking_health(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    assert client.get("/applications").status_code == 401
    assert client.get("/health").status_code == 200
