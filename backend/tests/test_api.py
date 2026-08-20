"""API integration tests: the full user workflow over HTTP with a fake SEC
backend and the mock LLM. TestClient executes background tasks synchronously,
so the pipeline has finished by the time the POST returns."""


def _create_research(client, question="What cloud infrastructure risks does the company face?"):
    company = client.get("/api/companies/search", params={"q": "EXCO"}).json()[0]
    filings = client.get(
        f"/api/companies/{company['cik']}/filings",
        params={"ticker": company["ticker"], "name": company["name"]},
    ).json()
    response = client.post("/api/research", json={
        "filing_id": filings[0]["id"],
        "task_type": "risk_factors",
        "question": question,
    })
    assert response.status_code == 202
    return response.json()["id"]


def test_company_search(client):
    response = client.get("/api/companies/search", params={"q": "EXCO"})
    assert response.status_code == 200
    assert response.json()[0]["ticker"] == "EXCO"


def test_full_workflow_to_approval(client):
    request_id = _create_research(client)

    status = client.get(f"/api/research/{request_id}").json()
    assert status["status"] == "awaiting_review"
    assert status["evidence"], "pipeline should extract evidence"
    for item in status["evidence"]:
        assert item["status"] in {"verified", "blocked"}
        assert item["accession_number"] == "0000012345-24-000001"
    assert status["brief"] is not None
    assert "not investment advice" in status["brief"]["content_markdown"].lower()
    agent_names = [run["agent_name"] for run in status["agent_runs"]]
    assert agent_names == ["evidence_extraction", "verification", "brief_writer"]

    review = client.post(f"/api/research/{request_id}/review",
                         json={"decision": "approved", "comment": "ok"})
    assert review.status_code == 200
    assert client.get(f"/api/research/{request_id}").json()["status"] == "approved"


def test_revision_cycle_produces_new_brief_version(client):
    request_id = _create_research(client)
    review = client.post(f"/api/research/{request_id}/review",
                         json={"decision": "revision_requested",
                               "comment": "Please shorten the summary."})
    assert review.status_code == 200
    assert review.json()["brief_version"] == 2
    status = client.get(f"/api/research/{request_id}").json()
    assert status["status"] == "awaiting_review"  # back to the human gate


def test_review_requires_awaiting_state(client):
    request_id = _create_research(client)
    client.post(f"/api/research/{request_id}/review",
                json={"decision": "rejected", "comment": ""})
    second = client.post(f"/api/research/{request_id}/review",
                         json={"decision": "approved", "comment": ""})
    assert second.status_code == 409


def test_audit_trail_records_workflow_and_verifies(client):
    request_id = _create_research(client)
    events = client.get("/api/audit", params={"request_id": request_id}).json()
    event_types = [e["event_type"] for e in events]
    assert "research_requested" in event_types
    assert "claim_verified" in event_types
    assert "brief_generated" in event_types
    # The fixture filing contains an injection attempt; it must be surfaced.
    assert "injection_warning" in event_types
    assert client.get("/api/audit/verify").json()["intact"] is True


def test_filing_is_fetched_only_once(client, fake_sec):
    _create_research(client)
    _create_research(client, question="What competition risks exist?")
    assert fake_sec.fetch_count == 1  # cached in DB after first ingest


def test_input_validation_rejects_bad_question(client):
    company = client.get("/api/companies/search", params={"q": "EXCO"}).json()[0]
    filings = client.get(
        f"/api/companies/{company['cik']}/filings",
        params={"ticker": "EXCO", "name": company["name"]},
    ).json()
    response = client.post("/api/research", json={
        "filing_id": filings[0]["id"], "task_type": "risk_factors", "question": "hi",
    })
    assert response.status_code == 422


def test_unknown_filing_404(client):
    response = client.post("/api/research", json={
        "filing_id": 999, "task_type": "risk_factors",
        "question": "What are the main risks?",
    })
    assert response.status_code == 404


def test_material_changes_requires_comparison_filing(client):
    company = client.get("/api/companies/search", params={"q": "EXCO"}).json()[0]
    filings = client.get(
        f"/api/companies/{company['cik']}/filings",
        params={"ticker": "EXCO", "name": company["name"]},
    ).json()
    response = client.post("/api/research", json={
        "filing_id": filings[0]["id"], "task_type": "material_changes",
        "question": "What changed since the previous filing?",
    })
    assert response.status_code == 422


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "mock"
