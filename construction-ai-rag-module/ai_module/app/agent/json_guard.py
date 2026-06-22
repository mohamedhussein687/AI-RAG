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
        if not decision.tool_calls:
            raise UnsafeDecisionError("database decision must include at least one tool call")
        for call in decision.tool_calls:
            if call.tool != "database_query":
                raise UnsafeDecisionError("unknown external tool")
            if not call.plan.table or not call.plan.operation:
                raise UnsafeDecisionError("database plan must include operation and table")
            if call.plan.limit < 1:
                raise UnsafeDecisionError("database plan limit must be positive")
    return decision
