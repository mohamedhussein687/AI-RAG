from __future__ import annotations

from contextlib import asynccontextmanager

from app.clients.llm_client import LlmClient

from .test_database_aware_chat import FakeConnection, chat_payload, schema_catalog


def test_agent_decide_contract_accepts_database_query_plan(client, auth_headers, monkeypatch):
    async def fake_decision(self, messages):
        return {
            "type": "tool_calls",
            "route": "database_query",
            "tool_calls": [
                {
                    "id": "db_1",
                    "tool": "database_query",
                    "plan": {
                        "operation": "count",
                        "table": "projects",
                        "filters": [],
                        "limit": 20,
                    },
                }
            ],
            "local_rag_results": [],
            "final_answer_instruction": "Answer in Arabic.",
        }

    monkeypatch.setattr(LlmClient, "chat_json", fake_decision)
    response = client.post("/api/agent/decide", headers=auth_headers, json=chat_payload("كام مشروع عندي؟", catalog=schema_catalog()))

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "tool_calls"
    assert data["route"] == "database_query"
    assert data["tool_calls"][0]["plan"]["table"] == "projects"
    assert "sql" not in str(data).lower()


def test_chat_contract_returns_answer_route_display_and_query_summary(client, auth_headers, monkeypatch):
    async def fake_decision(self, messages):
        return {
            "type": "tool_calls",
            "route": "database_query",
            "tool_calls": [
                {
                    "id": "db_1",
                    "tool": "database_query",
                    "plan": {
                        "operation": "count",
                        "table": "projects",
                        "filters": [],
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
        yield FakeConnection([{"count": 12}])

    monkeypatch.setattr("app.agent.database_chat_service.readonly_mysql_connection", fake_mysql)
    response = client.post("/api/chat", headers=auth_headers, json=chat_payload("كام مشروع عندي؟"))

    assert response.status_code == 200
    data = response.json()
    assert set(data) >= {"answer", "route", "display", "executed_query_summary", "sources"}
    assert data["route"] == "database_query"
    assert data["display"]["type"] == "metric"
    assert data["executed_query_summary"]["operation"] == "count"
    assert data["executed_query_summary"]["tables"] == ["projects"]
