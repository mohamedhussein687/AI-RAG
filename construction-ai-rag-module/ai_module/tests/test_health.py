def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["dependencies"]["postgres"] == "ok"
    assert data["dependencies"]["qdrant"] == "ok"
    assert data["dependencies"]["llm"] in {"ok", "disabled"}
