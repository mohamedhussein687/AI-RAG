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


def test_empty_delayed_projects_report_returns_clear_arabic_message(client, auth_headers):
    response = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv_123",
        "message": "هل يمكنك اعطائي تقرير باخر اربع مشاريع متأخرين في التسليم",
        "locale": "ar",
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"operation": "select", "intent": "delayed_projects_report", "table": "projects", "rows": []}}],
        "local_rag_results": [],
    })
    assert response.status_code == 200
    assert response.json()["answer"] == "لا توجد مشاريع متأخرة في التسليم حسب البيانات الحالية."


def test_empty_project_details_returns_clear_arabic_message(client, auth_headers):
    response = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv",
        "message": "اريد معلومات عن المشروع test60",
        "locale": "ar",
        "conversation_history": [],
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"operation": "details", "intent": "project_details", "table": "projects", "lookup_value": "test60", "rows": []}}],
        "local_rag_results": [],
        "final_answer_instruction": "Answer in Arabic.",
    })
    assert response.status_code == 200
    assert response.json()["answer"] == "لم أجد مشروعًا باسم أو كود test60 في البيانات الحالية."


def test_latest_project_answer_is_deterministic_arabic(client, auth_headers, monkeypatch):
    async def should_not_call_llm(*_args, **_kwargs):
        raise AssertionError("latest_project answer should be formatted deterministically")

    from app.clients.llm_client import LlmClient
    monkeypatch.setattr(LlmClient, "chat_json", should_not_call_llm)
    response = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv",
        "message": "ما هو اخر مشروع تم اضافتة",
        "locale": "ar",
        "conversation_history": [],
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"operation": "select", "intent": "latest_project", "table": "projects", "rows": [{"title": "costa", "project_code": "c832 - p2 - 06-2026", "status": 2, "created_at": "2026-06-19", "updated_at": "2026-06-20"}]}}],
        "local_rag_results": [],
        "final_answer_instruction": "Answer in Arabic.",
    })
    assert response.status_code == 200
    answer = response.json()["answer"]
    assert answer == "آخر مشروع تم إضافته هو: costa، الكود: c832 - p2 - 06-2026، الحالة: 2، تاريخ الإضافة: 2026-06-19، آخر تحديث: 2026-06-20."


def test_project_details_by_code_answer_is_deterministic_arabic(client, auth_headers, monkeypatch):
    async def should_not_call_llm(*_args, **_kwargs):
        raise AssertionError("project code details answer should be formatted deterministically")

    from app.clients.llm_client import LlmClient
    monkeypatch.setattr(LlmClient, "chat_json", should_not_call_llm)
    response = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv",
        "message": "عاوز بيانات عن المشروع صاخب الكود c832 - p2 - 06-2026",
        "locale": "ar",
        "conversation_history": [],
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"operation": "details", "intent": "project_details", "lookup_type": "project_code", "table": "projects", "lookup_value": "c832-p2-06-2026", "rows": [{"title": "costa", "project_code": "c832 - p2 - 06-2026", "status": 2, "planned_delivery_date": "2026-08-01", "updated_at": "2026-06-20"}]}}],
        "local_rag_results": [],
        "final_answer_instruction": "Answer in Arabic.",
    })
    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "بيانات المشروع: costa" in answer
    assert "الكود: c832 - p2 - 06-2026" in answer
    assert "تاريخ التسليم/النهاية: 2026-08-01" in answer


def test_missing_project_code_answer_is_specific(client, auth_headers):
    response = client.post("/api/agent/final", headers=auth_headers, json={
        "conversation_id": "conv",
        "message": "تفاصيل مشروع بالكود C832-P2-06-2026",
        "locale": "ar",
        "conversation_history": [],
        "tool_results": [{"tool_call_id": "db_1", "tool": "database_query", "result": {"operation": "details", "intent": "project_details", "lookup_type": "project_code", "table": "projects", "lookup_value": "c832-p2-06-2026", "rows": []}}],
        "local_rag_results": [],
        "final_answer_instruction": "Answer in Arabic.",
    })
    assert response.status_code == 200
    assert response.json()["answer"] == "لم أجد مشروعًا بالكود c832-p2-06-2026 في البيانات الحالية."


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
