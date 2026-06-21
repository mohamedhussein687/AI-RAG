from typing import Any
from pydantic import TypeAdapter
from app.common.errors import UnsafeDecisionError
from app.schemas import AgentDecision, contains_forbidden_keys

DecisionAdapter = TypeAdapter(AgentDecision)


def validate_decision(payload: Any) -> AgentDecision:
    if contains_forbidden_keys(payload):
        raise UnsafeDecisionError("decision contains forbidden raw SQL/query keys")
    decision = DecisionAdapter.validate_python(payload)
    if getattr(decision, "type", None) == "tool_calls":
        for call in decision.tool_calls:
            if call.tool != "database_query":
                raise UnsafeDecisionError("unknown external tool")
    return decision
