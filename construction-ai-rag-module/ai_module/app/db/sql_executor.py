from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.db.sql_compiler import CompiledQuery
from app.schema.schema_models import QueryExecution


LONG_SECRET_PATTERN = re.compile(r"(?i)(password|secret|token|key)\s*[=:]?\s*['\"]?[A-Za-z0-9_./+=-]{8,}")


class QueryExecutor:
    def __init__(self, connection: Any, *, max_rows: int = 200, timeout_seconds: int = 15):
        self.connection = connection
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds

    async def execute(self, query: CompiledQuery) -> QueryExecution:
        if not query.sql.lstrip().lower().startswith("select "):
            raise ValueError("only read-only SELECT queries may be executed")
        started = time.perf_counter()
        try:
            rows = await asyncio.wait_for(self._execute(query), timeout=self.timeout_seconds)
        except Exception as exc:
            raise RuntimeError(redact_database_error(str(exc))) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000
        return QueryExecution(
            rows=rows[: self.max_rows],
            elapsed_ms=elapsed_ms,
            summary={
                "operation": query.operation,
                "table": query.table,
                "columns": query.columns,
                "row_count": min(len(rows), self.max_rows),
                "truncated": len(rows) > self.max_rows,
            },
        )

    async def _execute(self, query: CompiledQuery) -> list[dict[str, Any]]:
        async with self.connection.cursor() as cursor:
            await cursor.execute(query.sql, query.parameters)
            rows = await cursor.fetchall()
        return [_serialize_row(row) for row in rows]


def redact_database_error(message: str) -> str:
    redacted = LONG_SECRET_PATTERN.sub(lambda match: match.group(0).split()[0] + " [REDACTED]", message)
    redacted = re.sub(r"(?i)(using password\s+)[^\s]+", r"\1[REDACTED]", redacted)
    return redacted


def _serialize_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)
