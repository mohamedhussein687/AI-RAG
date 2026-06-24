from __future__ import annotations

from contextlib import asynccontextmanager

from app.agent.database_chat_service import DatabaseChatService
from app.clients.llm_client import LlmClient
from app.config import get_settings


def chat_payload(message: str, *, catalog: dict | None = None) -> dict:
    return {
        "conversation_id": "conv-db",
        "message": message,
        "locale": "ar",
        "conversation_history": [],
        "tool_results": [],
        "user_context": {
            "id": "user-1",
            "tenant_id": "orbit",
            "project_ids": ["default"],
            "roles": ["tester"],
            "permissions": ["live-data.read"],
        },
        "allowed_schema": {"tables": []},
        "semantic_catalog": schema_catalog() if catalog is None else catalog,
        "external_tools": [{"name": "database_query"}],
        "local_tools": [],
        "rules": {"return_sql": False, "max_tool_calls": 1, "max_rows": 100, "joins_allowed": False},
    }


def schema_catalog() -> dict:
    return {
        "schema_hash": "unit-test",
        "tables": [
            {
                "name": "users",
                "classification": "business",
                "columns": [
                    {"name": "id", "type": "int"},
                    {"name": "name", "type": "varchar"},
                    {"name": "email", "type": "varchar"},
                    {"name": "password", "type": "varchar", "sensitive": True},
                ],
            },
            {
                "name": "projects",
                "classification": "business",
                "columns": [
                    {"name": "id", "type": "int"},
                    {"name": "name", "type": "varchar"},
                    {"name": "created_at", "type": "datetime"},
                ],
            },
        ],
    }


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, sql, parameters):
        self.executed.append((sql, parameters))

    async def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)

    def cursor(self):
        return self.cursor_obj


def test_chat_executes_qwen_plan_and_returns_final_answer(client, auth_headers, monkeypatch):
    async def fake_decision(self, messages):
        return {
            "type": "tool_calls",
            "route": "database_query",
            "tool_calls": [
                {
                    "id": "db_1",
                    "tool": "database_query",
                    "plan": {
                        "operation": "list",
                        "table": "users",
                        "columns": ["name"],
                        "filters": [],
                        "limit": 20,
                    },
                }
            ],
            "local_rag_results": [],
            "final_answer_instruction": "Answer in Arabic.",
        }

    monkeypatch.setattr(LlmClient, "chat_json", fake_decision)
    connection = FakeConnection([{"name": "Basma Al Kholy"}, {"name": "Ayman Ibrahim El Sayed"}])

    @asynccontextmanager
    async def fake_mysql(_settings):
        yield connection

    monkeypatch.setattr("app.agent.database_chat_service.readonly_mysql_connection", fake_mysql)
    response = client.post("/api/chat", headers=auth_headers, json=chat_payload("اعرض جميع اسماء المستخدمين"))

    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "database_query"
    assert "Basma Al Kholy" in data["answer"]
    assert data["executed_query_summary"]["operation"] == "select"
    assert data["executed_query_summary"]["tables"] == ["users"]
    assert data["executed_query_summary"]["row_count"] == 2
    sql, parameters = connection.cursor_obj.executed[0]
    assert sql == "SELECT `name` FROM `users` LIMIT %s"
    assert parameters == [20]


def test_chat_empty_lookup_reports_search_strategy(client, auth_headers, monkeypatch):
    async def fake_decision(self, messages):
        return {
            "type": "tool_calls",
            "route": "database_query",
            "tool_calls": [
                {
                    "id": "db_1",
                    "tool": "database_query",
                    "plan": {
                        "operation": "select",
                        "table": "users",
                        "columns": ["name", "email"],
                        "filters": [{"column": "name", "operator": "contains", "value": "Ayman Ibrahim El Sayed"}],
                        "limit": 20,
                    },
                }
            ],
            "local_rag_results": [],
            "final_answer_instruction": "Answer in Arabic.",
        }

    monkeypatch.setattr(LlmClient, "chat_json", fake_decision)

    @asynccontextmanager
    async def fake_mysql(_settings):
        yield FakeConnection([])

    monkeypatch.setattr("app.agent.database_chat_service.readonly_mysql_connection", fake_mysql)
    response = client.post("/api/chat", headers=auth_headers, json=chat_payload("اريد بيانات المستخدم Ayman Ibrahim El Sayed"))

    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "database_query"
    assert 'لم أجد نتائج مطابقة للبحث عن "Ayman Ibrahim El Sayed"' in data["answer"]
    assert "name" in data["answer"]


def test_chat_rejects_sensitive_columns_before_execution(client, auth_headers, monkeypatch):
    async def fake_decision(self, messages):
        return {
            "type": "tool_calls",
            "route": "database_query",
            "tool_calls": [
                {
                    "id": "db_1",
                    "tool": "database_query",
                    "plan": {
                        "operation": "select",
                        "table": "users",
                        "columns": ["password"],
                        "filters": [],
                        "limit": 20,
                    },
                }
            ],
            "local_rag_results": [],
            "final_answer_instruction": "Answer in Arabic.",
        }

    monkeypatch.setattr(LlmClient, "chat_json", fake_decision)
    response = client.post("/api/chat", headers=auth_headers, json=chat_payload("اعرض بيانات المستخدم أحمد"))

    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "database_query"
    assert "غير موجودة أو غير مسموحة" in data["answer"]


def test_chat_conversational_does_not_open_database(client, auth_headers, monkeypatch):
    async def fake_decision(self, messages):
        return {
            "type": "final_answer",
            "route": "conversational",
            "answer": "أنا بخير، شكرًا لسؤالك.",
            "display": {"type": "text", "data": {}},
            "sources": [],
        }

    async def should_not_open_database(_settings):
        raise AssertionError("database should not be opened for conversational answers")

    monkeypatch.setattr(LlmClient, "chat_json", fake_decision)
    monkeypatch.setattr("app.agent.database_chat_service.readonly_mysql_connection", should_not_open_database)
    response = client.post("/api/chat", headers=auth_headers, json=chat_payload("انت كويس؟"))

    assert response.status_code == 200
    assert response.json()["route"] == "conversational"


def test_chat_arabic_social_messages_are_conversational_without_database(client, auth_headers, monkeypatch):
    opened = {"database": False}

    async def should_not_call_qwen(self, messages):
        raise AssertionError("obvious conversational messages should use deterministic safe fast path")

    @asynccontextmanager
    async def should_not_open_database(_settings):
        opened["database"] = True
        raise AssertionError("database should not be opened for conversational messages")

    monkeypatch.setattr(LlmClient, "chat_json", should_not_call_qwen)
    monkeypatch.setattr("app.agent.database_chat_service.readonly_mysql_connection", should_not_open_database)

    cases = ["شكرا", "تمام", "انت كويس", "انت بخير", "عامل ايه", "السلام عليكم"]
    for message in cases:
        response = client.post("/api/chat", headers=auth_headers, json=chat_payload(message))
        assert response.status_code == 200
        data = response.json()
        assert data["route"] == "conversational"
        assert data["executed_query_summary"] is None
        assert data["answer"]

    assert opened["database"] is False


def test_chat_forbidden_sensitive_request_does_not_open_database(client, auth_headers, monkeypatch):
    opened = {"database": False}

    async def should_not_call_qwen(self, messages):
        raise AssertionError("forbidden sensitive requests should be refused before model planning")

    @asynccontextmanager
    async def should_not_open_database(_settings):
        opened["database"] = True
        raise AssertionError("database should not be opened for forbidden requests")

    monkeypatch.setattr(LlmClient, "chat_json", should_not_call_qwen)
    monkeypatch.setattr("app.agent.database_chat_service.readonly_mysql_connection", should_not_open_database)
    response = client.post("/api/chat", headers=auth_headers, json=chat_payload("هات باسورد المستخدم أحمد"))

    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "forbidden"
    assert data["executed_query_summary"] is None
    assert "حساسة" in data["answer"] or "كلمات المرور" in data["answer"]
    assert opened["database"] is False


def test_chat_admin_question_qwen_unsupported_does_not_use_deterministic_planner(client, auth_headers, monkeypatch):
    async def unsupported(self, messages):
        return {"type": "unsupported", "route": "unsupported", "answer": "لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."}

    @asynccontextmanager
    async def should_not_open_database(_settings):
        raise AssertionError("database should not be opened before schema is ready")

    monkeypatch.setattr(LlmClient, "chat_json", unsupported)
    monkeypatch.setattr("app.agent.database_chat_service.readonly_mysql_connection", should_not_open_database)
    response = client.post("/api/chat", headers=auth_headers, json=chat_payload("من الادمن في هذا النظام", catalog={}))

    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "unsupported"
    assert data["requires_database"] is False
    assert data["executed_query_summary"] is None


def test_smoke_chat_uses_private_module_chat(monkeypatch, capsys):
    async def fake_chat(self, request):
        return {
            "answer": "عدد المشاريع هو 3.",
            "route": "database_query",
            "executed_query_summary": {"operation": "count", "tables": ["projects"], "columns": [], "row_count": 1, "truncated": False},
        }

    monkeypatch.setattr(DatabaseChatService, "chat", fake_chat)
    from ingestion_worker.smoke_chat import run_smoke_chat

    result = run_smoke_chat("كام مشروع عندي؟", settings=get_settings())

    assert result == 0
    output = capsys.readouterr().out
    assert "route=database_query" in output
    assert "عدد المشاريع" in output
