from app.rag.document_service import chunks
from .conftest import index_policy


def test_document_indexing_creates_chunks(client, auth_headers):
    response = index_policy(client, auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "indexed"
    assert data["chunks_indexed"] >= 1
    assert chunks


def test_blank_document_content_is_rejected_without_partial_entries(client, auth_headers):
    response = client.post("/api/rag/documents", headers=auth_headers, json={
        "tenant_id": "3",
        "project_id": "22",
        "title": "فارغ",
        "source_type": "policy",
        "content": "   \n\t   ",
        "access_policy": {"permissions": ["docs.view"]},
        "metadata": {},
    })
    assert response.status_code == 422
    assert chunks == {}


def test_indexed_chunks_include_access_payload_fields(client, auth_headers):
    from app.rag.document_service import chunk_payloads

    response = index_policy(client, auth_headers)
    assert response.status_code == 201
    payload = next(iter(chunk_payloads.values()))
    assert payload["tenant_id"] == "3"
    assert payload["project_id"] == "22"
    assert payload["document_id"] == response.json()["document_id"]
    assert payload["permissions"] == ["docs.view", "policies.view"]
    assert payload["content_hash"]


def test_document_status_becomes_indexed_after_chunks_are_available(client, auth_headers):
    from app.rag.document_service import documents, chunks

    response = index_policy(client, auth_headers)
    document = documents[response.json()["document_id"]]
    assert document.status == "indexed"
    assert chunks
