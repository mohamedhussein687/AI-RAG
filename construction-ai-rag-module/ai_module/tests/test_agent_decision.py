from .conftest import index_policy
from app.clients.llm_client import LlmClient


def decide_payload(message, allowed=True, semantic_catalog=None):
    tables = [{"name": "projects", "columns": ["id", "status", "tenant_id"], "allowed_operations": ["count", "list"]}] if allowed else []
    return {
        "conversation_id": "conv_123",
        "message": message,
        "locale": "ar",
        "conversation_history": [],
        "user_context": {"id": "15", "tenant_id": "3", "roles": ["manager"], "permissions": ["projects.view", "docs.view", "policies.view"], "project_ids": ["22"]},
        "allowed_schema": {"tables": tables},
        "semantic_catalog": semantic_catalog or {},
        "external_tools": [{"name": "database_query"}],
        "local_tools": [{"name": "knowledge_search"}],
        "rules": {"return_sql": False, "max_tool_calls": 5, "max_rows": 100, "joins_allowed": False},
    }


def invoice_catalog():
    return {
        "catalog_version": 2,
        "schema_hash": "test",
        "tables": [
            {
                "name": "invoices",
                "entity_ar": ["فاتورة", "فواتير"],
                "entity_en": ["invoices", "invoice"],
                "allowed_operations": ["count", "list", "group_count"],
                "columns": [
                    {"name": "id", "type": "number", "operations": ["filter", "sort"], "enum_values": []},
                    {"name": "created_at", "type": "date", "operations": ["filter", "sort", "group"], "enum_values": []},
                ],
            }
        ],
    }


def project_catalog_with_cms_table():
    return {
        "catalog_version": 3,
        "schema_hash": "test",
        "domain_entities": [
            {"entity": "projects", "table": "projects", "purpose": "operational construction projects", "count_operation": "count"}
        ],
        "tables_index": [
            {"name": "about_us", "allowed_operations": ["count", "list"]},
            {"name": "projects", "allowed_operations": ["count", "list", "group_count"]},
        ],
        "tables": [
            {
                "name": "projects",
                "allowed_operations": ["count", "list", "group_count"],
                "columns": [
                    {"name": "status", "type": "string", "operations": ["filter", "group"], "enum_values": ["waiting"]},
                    {"name": "created_at", "type": "date", "operations": ["filter", "sort", "group"], "enum_values": []},
                ],
            }
        ],
    }


def qwen_count_invoices(*_args, **_kwargs):
    return {
        "type": "tool_calls",
        "tool_calls": [
            {"id": "db_1", "tool": "database_query", "plan": {"operation": "count", "table": "invoices", "filters": [], "limit": 20}}
        ],
        "local_rag_results": [],
        "final_answer_instruction": "Answer in Arabic.",
    }


def qwen_identity(*_args, **_kwargs):
    return {
        "type": "final_answer",
        "answer": "أنا مساعد ORBIT AI، شغال على مشروع ORBIT، وأقدر أساعدك في قراءة وتحليل بيانات المشروع حسب الصلاحيات المتاحة.",
        "display": {"type": "text", "data": {}},
        "sources": [],
    }


def test_decide_returns_qwen_database_query(client, auth_headers, monkeypatch):
    async def fake_chat_json(self, messages):
        assert "semantic_catalog" in messages[1]["content"]
        return qwen_count_invoices()

    monkeypatch.setattr(LlmClient, "chat_json", fake_chat_json)
    response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload("كم فاتورة موجودة؟", semantic_catalog=invoice_catalog()))
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "tool_calls"
    assert data["tool_calls"][0]["tool"] == "database_query"
    assert data["tool_calls"][0]["plan"]["operation"] == "count"
    assert data["tool_calls"][0]["plan"]["table"] == "invoices"
    assert "sql" not in str(data).lower()


def test_identity_question_is_handled_by_qwen(client, auth_headers, monkeypatch):
    async def fake_chat_json(self, messages):
        assert "انت مين؟" in messages[1]["content"]
        return qwen_identity()

    monkeypatch.setattr(LlmClient, "chat_json", fake_chat_json)
    response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload("انت مين؟", semantic_catalog=invoice_catalog()))
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "final_answer"
    assert data["answer"].startswith("أنا مساعد ORBIT AI")


def test_small_talk_question_is_qwen_final_answer_without_database_query(client, auth_headers, monkeypatch):
    async def fake_chat_json(self, messages):
        return {
            "type": "final_answer",
            "answer": "أنا بخير، جاهز أساعدك في بيانات مشروع ORBIT.",
            "display": {"type": "text", "data": {}},
            "sources": [],
        }

    monkeypatch.setattr(LlmClient, "chat_json", fake_chat_json)
    response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload("هل انت بخير؟", semantic_catalog=project_catalog_with_cms_table()))
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "final_answer"
    assert "tool_calls" not in data
    assert "بخير" in data["answer"]


def test_project_count_uses_authoritative_projects_table_not_about_us(client, auth_headers, monkeypatch):
    async def should_not_call_qwen(self, messages):
        raise AssertionError("project_count guard should run before LLM table selection")

    monkeypatch.setattr(LlmClient, "chat_json", should_not_call_qwen)
    for question in ["كم عدد المشاريع؟", "عدد المشاريع"]:
        response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload(question, semantic_catalog=project_catalog_with_cms_table()))
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "tool_calls"
        plan = data["tool_calls"][0]["plan"]
        assert plan["operation"] == "count"
        assert plan["table"] == "projects"
        assert plan["table"] != "about_us"


def test_equivalent_invoice_questions_generate_same_plan(client, auth_headers, monkeypatch):
    async def fake_chat_json(self, messages):
        return qwen_count_invoices()

    monkeypatch.setattr(LlmClient, "chat_json", fake_chat_json)
    questions = [
        "كم فاتورة موجودة؟",
        "عدد الفواتير الموجودة كام؟",
        "الفواتير الموجودة عددها كام؟",
        "عاوز أعرف عدد الفواتير",
    ]
    plans = []
    for question in questions:
        response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload(question, semantic_catalog=invoice_catalog()))
        assert response.status_code == 200
        plans.append(response.json()["tool_calls"][0]["plan"])
    assert plans[0] == plans[1] == plans[2] == plans[3]


def test_decide_uses_local_rag_for_how_to(client, auth_headers):
    index_policy(client, auth_headers)
    response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload("إزاي أضيف مستخلص؟"))
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "final_answer"
    assert data["sources"]


def test_decide_uses_rag_plus_database_query_for_policy_delay(client, auth_headers):
    index_policy(client, auth_headers)
    response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload("هل مشروع العاصمة محتاج تصعيد حسب السياسة؟ المشروع متأخر"))
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "unsupported"


def test_forbidden_for_password(client, auth_headers):
    response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload("هات password المستخدم"))
    assert response.status_code == 200
    assert response.json()["type"] == "forbidden"


def test_no_raw_sql_can_appear_in_agent_decisions(client, auth_headers):
    response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload("كم مشروع waiting؟", semantic_catalog=invoice_catalog()))
    text = str(response.json()).lower()
    assert "raw_sql" not in text
    assert "select " not in text
    assert " query" not in text


def test_unknown_business_question_still_returns_safe_unsupported(client, auth_headers, monkeypatch):
    async def fake_chat_json(self, messages):
        return {"type": "unsupported", "answer": "لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."}

    monkeypatch.setattr(LlmClient, "chat_json", fake_chat_json)
    response = client.post("/api/agent/decide", headers=auth_headers, json=decide_payload("كم عدد العقود المؤرشفة؟", semantic_catalog=project_catalog_with_cms_table()))
    assert response.status_code == 200
    assert response.json()["type"] == "unsupported"
