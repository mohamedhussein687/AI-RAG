import pytest

from app.db.sql_compiler import CompiledQuery
from app.db.sql_executor import QueryExecutor, redact_database_error


class FakeCursor:
    def __init__(self, rows=None, error: Exception | None = None):
        self.rows = rows or [{"name": "Ayman"}]
        self.error = error
        self.executed = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, sql, parameters):
        self.executed = (sql, parameters)
        if self.error:
            raise self.error

    async def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


@pytest.mark.asyncio
async def test_executor_returns_rows_and_summary() -> None:
    cursor = FakeCursor(rows=[{"name": "Basma"}])
    executor = QueryExecutor(FakeConnection(cursor), max_rows=20)

    result = await executor.execute(CompiledQuery(sql="SELECT `name` FROM `users` LIMIT %s", parameters=[20], table="users", operation="select", columns=["name"]))

    assert result.rows == [{"name": "Basma"}]
    assert result.summary["table"] == "users"
    assert result.summary["row_count"] == 1
    assert cursor.executed == ("SELECT `name` FROM `users` LIMIT %s", [20])


@pytest.mark.asyncio
async def test_executor_blocks_non_select_queries() -> None:
    executor = QueryExecutor(FakeConnection(FakeCursor()))

    with pytest.raises(ValueError, match="read-only"):
        await executor.execute(CompiledQuery(sql="DELETE FROM users", parameters=[], table="users", operation="select", columns=[]))


def test_redact_database_error_hides_password_like_values() -> None:
    redacted = redact_database_error("Access denied for user test using password h6G7uEUdHZv7C6Uz167vNHeBS")

    assert "h6G7uEUdHZv7C6Uz167vNHeBS" not in redacted
    assert "[REDACTED]" in redacted
