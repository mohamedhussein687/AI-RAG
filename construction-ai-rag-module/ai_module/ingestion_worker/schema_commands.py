from __future__ import annotations

import json
from typing import Any

from app.config import Settings, get_settings
from app.db.mysql import MySqlConnectionError
from app.schema.schema_service import SchemaService


async def run_schema_command(
    command: str,
    *,
    source: str,
    force: bool = False,
    as_json: bool = False,
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    service = SchemaService(settings)
    try:
        if command == "schema-ingest":
            payload = await service.ingest_current(source, force=force)
        elif command == "schema-refresh":
            payload = await service.ingest_current(source, force=True)
        elif command == "schema-status":
            status = await service.status(source)
            payload = status if isinstance(status, dict) else status.model_dump()
        else:
            raise ValueError(f"unsupported schema command: {command}")
    except MySqlConnectionError as exc:
        payload = {"source": source, "status": "failed", "error": str(exc)}
        print(format_schema_status(payload, as_json=as_json))
        return 2
    print(format_schema_status(payload, as_json=as_json))
    return 0


def format_schema_status(payload: dict[str, Any], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    schema_hash = _short(payload.get("schema_hash"))
    alias_hash = _short(payload.get("alias_hash"))
    error = payload.get("error")
    return (
        f"source={payload.get('source')} status={payload.get('status')} "
        f"database={payload.get('database_name')} schema_hash={schema_hash} alias_hash={alias_hash} "
        f"tables={payload.get('table_count', 0)} columns={payload.get('column_count', 0)} "
        f"sensitive_fields={payload.get('sensitive_field_count', 0)} stale_reason={payload.get('stale_reason')} "
        f"error={error}"
    )


def _short(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:8]
