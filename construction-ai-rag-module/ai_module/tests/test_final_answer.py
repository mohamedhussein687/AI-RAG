from .conftest import index_policy
from app.clients.llm_client import LlmClient


def test_final_database_answer_uses_qwen_when_llm_enabled(client, auth_headers, monkeypatch):
    async def fake_chat_json(self, messages):
        assert "query_results" in messages[1]["content"]
        return {"answer": "عدد الفواتير الموجودة في النظام هو 27,193 فاتورة."}

    monkeypatch.setenv("FAKE_LLM", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(LlmClient, "chat_json", fake_chat_json)
    response = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv_123",
        "message": "عدد الفواتير الموجودة كام؟",
        "locale": "ar",
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"operation": "count", "table": "invoices", "count": 27193}}],
        "local_rag_results": [],
    })
    assert response.status_code == 200
    assert response.json()["answer"] == "عدد الفواتير الموجودة في النظام هو 27,193 فاتورة."
    get_settings.cache_clear()


def test_final_answer_includes_sources_when_rag_is_used(client, auth_headers):
    index_policy(client, auth_headers)
    search = client.post("/api/rag/search", headers=auth_headers, json={"query": "تأخر المشروع", "user_context": {"tenant_id": "3", "project_ids": ["22"], "permissions": ["docs.view", "policies.view"]}, "top_k": 1, "filters": {"project_id": "22"}})
    chunks = search.json()["results"]
    response = client.post("/api/agent/final", headers=auth_headers, json={"conversation_id": "conv_123", "message": "ليه مشروع العاصمة متأخر؟", "locale": "ar", "conversation_history": [], "tool_results": [], "local_rag_results": chunks, "final_answer_instruction": ""})
    assert response.status_code == 200
    data = response.json()
    assert data["sources"]
    assert data["display"]["type"] == "answer_with_sources"


def test_final_answer_display_types_for_metric_table_mixed_and_insufficient(client, auth_headers):
    metric = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv_123",
        "message": "كم مشروع waiting؟",
        "locale": "ar",
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"count": 4}}],
        "local_rag_results": [],
    })
    assert metric.status_code == 200
    assert metric.json()["display"]["type"] == "metric"

    table = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv_123",
        "message": "اعرض المشاريع",
        "locale": "ar",
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"rows": [{"name": "A"}]}}],
        "local_rag_results": [],
    })
    assert table.status_code == 200
    assert table.json()["display"]["type"] == "table"

    index_policy(client, auth_headers)
    search = client.post("/api/rag/search", headers=auth_headers, json={"query": "تأخر المشروع", "user_context": {"tenant_id": "3", "project_ids": ["22"], "permissions": ["docs.view", "policies.view"]}, "top_k": 1, "filters": {"project_id": "22"}})
    mixed = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv_123",
        "message": "هل يحتاج تصعيد؟",
        "locale": "ar",
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"count": 1}}],
        "local_rag_results": search.json()["results"],
    })
    assert mixed.status_code == 200
    assert mixed.json()["display"]["type"] == "mixed"
    assert mixed.json()["sources"]

    insufficient = client.post("/api/agent/final", headers=auth_headers, json={"conversation_id": "conv_123", "message": "؟", "locale": "ar"})
    assert insufficient.status_code == 200
    assert insufficient.json()["display"]["type"] == "text"
    assert "لا توجد نتائج كافية" in insufficient.json()["answer"]
