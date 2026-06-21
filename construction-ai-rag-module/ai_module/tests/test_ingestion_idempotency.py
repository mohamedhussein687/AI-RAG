from .conftest import index_policy
from app.rag.document_service import chunks, documents


def test_duplicate_index_after_success_reuses_stable_document(client, auth_headers):
    first = index_policy(client, auth_headers)
    second = index_policy(client, auth_headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["document_id"] == second.json()["document_id"]
    assert first.json()["chunks_indexed"] == second.json()["chunks_indexed"]
    assert len(documents) == 1


def test_delete_followed_by_reindex_uses_same_stable_identity_in_local_mode(client, auth_headers):
    first = index_policy(client, auth_headers)
    doc_id = first.json()["document_id"]
    documents.pop(doc_id)
    chunks.clear()
    second = index_policy(client, auth_headers)
    assert second.json()["document_id"] == doc_id
    assert chunks


def test_tenant_isolated_duplicate_identity(client, auth_headers):
    first = index_policy(client, auth_headers, tenant="3")
    second = index_policy(client, auth_headers, tenant="tenant-b")
    assert first.json()["document_id"] != second.json()["document_id"]
