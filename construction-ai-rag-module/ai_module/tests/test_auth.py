from app.common.logging import redact


def test_auth_required(client):
    response = client.post("/api/rag/search", json={"query": "test", "user_context": {"tenant_id": "3", "permissions": ["docs.view"]}})
    assert response.status_code == 401


def test_token_redaction_behavior():
    data = redact({"Authorization": "Bearer secret", "nested": {"spring_gateway_token": "secret", "safe": "ok"}})
    assert data["Authorization"] == "[REDACTED]"
    assert data["nested"]["spring_gateway_token"] == "[REDACTED]"
    assert data["nested"]["safe"] == "ok"
