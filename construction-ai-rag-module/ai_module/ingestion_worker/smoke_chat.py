from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent.database_chat_service import DatabaseChatService
from app.config import Settings, get_settings
from app.schemas import AgentDecideRequest


def run_smoke_chat(message: str, *, source: str = "construction_mysql", settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    response = asyncio.run(_chat(message, source=source, settings=settings))
    summary = response.get("executed_query_summary")
    print(f"route={response.get('route')}")
    print(f"answer={_short(response.get('answer'))}")
    if summary:
        print("executed_query_summary=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


async def _chat(message: str, *, source: str, settings: Settings) -> dict[str, Any]:
    request = AgentDecideRequest(
        conversation_id="smoke-chat",
        message=message,
        locale="ar",
        user_context={
            "id": "smoke",
            "tenant_id": source,
            "project_ids": ["default"],
            "roles": ["smoke"],
            "permissions": ["live-data.read"],
        },
        semantic_catalog={"source_name": source, "schema_hash": "smoke-runtime"},
        external_tools=[{"name": "database_query"}],
        local_tools=[],
        rules={"return_sql": False, "max_tool_calls": 1, "max_rows": settings.mysql_max_rows, "joins_allowed": False},
    )
    response = await DatabaseChatService(settings).chat(request)
    return response if isinstance(response, dict) else response.model_dump()


def _short(value: Any, limit: int = 500) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "..."
