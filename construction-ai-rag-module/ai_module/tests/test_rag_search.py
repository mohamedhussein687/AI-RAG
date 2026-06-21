from .conftest import index_policy


def search(client, auth_headers, tenant="3", project_ids=None, permissions=None):
    return client.post("/api/rag/search", headers=auth_headers, json={
        "query": "خطوات التعامل مع تأخر المشروع",
        "user_context": {"tenant_id": tenant, "project_ids": ["22"] if project_ids is None else project_ids, "permissions": permissions or ["docs.view", "policies.view"]},
        "top_k": 5,
        "filters": {"document_types": ["policy"], "project_id": "22"},
    })


def test_rag_search_respects_tenant_id(client, auth_headers):
    index_policy(client, auth_headers, tenant="3")
    response = search(client, auth_headers, tenant="9")
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_rag_search_respects_permissions(client, auth_headers):
    index_policy(client, auth_headers)
    response = search(client, auth_headers, permissions=["docs.view"])
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_arabic_query_retrieves_arabic_chunks(client, auth_headers):
    index_policy(client, auth_headers)
    response = search(client, auth_headers)
    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    assert "تأخر" in results[0]["text"] or "مستخلص" in results[0]["text"]


def test_rag_search_requires_explicit_project_access_for_project_chunks(client, auth_headers):
    index_policy(client, auth_headers)
    response = search(client, auth_headers, project_ids=[])
    assert response.status_code == 200
    assert response.json()["results"] == []
