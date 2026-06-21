from pydantic import TypeAdapter
from app.schemas import AgentDecision
from app.agent.json_guard import validate_decision
import pytest


def test_response_schemas_validate():
    adapter = TypeAdapter(AgentDecision)
    decision = adapter.validate_python({"type": "clarification", "question": "وضح؟"})
    assert decision.type == "clarification"


def test_json_guard_rejects_sql_key():
    with pytest.raises(Exception):
        validate_decision({"type": "tool_calls", "raw_sql": "select 1", "tool_calls": [], "local_rag_results": [], "final_answer_instruction": ""})


def test_settings_can_be_overridden_from_environment(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("CHAT_MODEL", "local-chat-test")
    monkeypatch.setenv("MAX_RETRIEVED_CHUNKS", "3")
    settings = Settings()
    assert settings.chat_model == "local-chat-test"
    assert settings.max_retrieved_chunks == 3
