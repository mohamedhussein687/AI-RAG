import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AI_MODULE_TOKEN", "test-token")
os.environ.setdefault("FAKE_LLM", "true")
os.environ.setdefault("FAKE_EMBEDDINGS", "true")
os.environ.setdefault("FAKE_RERANKER", "true")

from app.config import get_settings
from app.main import app
from app.rag.document_service import documents, chunks, chunk_payloads
from app.rag.qdrant_service import qdrant


@pytest.fixture(autouse=True)
def clean_state():
    get_settings.cache_clear()
    documents.clear()
    chunks.clear()
    chunk_payloads.clear()
    qdrant.points.clear()
    yield
    documents.clear()
    chunks.clear()
    chunk_payloads.clear()
    qdrant.points.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


def index_policy(client, auth_headers, tenant="3", project="22", permissions=None):
    permissions = permissions or ["docs.view", "policies.view"]
    return client.post("/api/rag/documents", headers=auth_headers, json={
        "tenant_id": tenant,
        "project_id": project,
        "title": "سياسة إدارة تأخير المشاريع",
        "source_type": "policy",
        "content": "إزاي أضيف مستخلص؟ يجب فتح شاشة المستخلصات وإدخال البنود. عند تأخر المشروع يجب مراجعة سبب التأخير ورفع التصعيد حسب السياسة.",
        "access_policy": {"permissions": permissions},
        "metadata": {"version": 1},
    })
