from __future__ import annotations

import pytest

from ingestion_worker.schema_commands import format_schema_status, run_schema_command


def test_schema_status_format_redacts_and_reports_counts():
    rendered = format_schema_status(
        {
            "source": "construction_mysql",
            "status": "fresh",
            "database_name": "construction_ai_dev",
            "schema_hash": "abcdef123456",
            "alias_hash": "fedcba654321",
            "table_count": 3,
            "column_count": 20,
            "sensitive_field_count": 2,
        },
        as_json=False,
    )

    assert "source=construction_mysql" in rendered
    assert "tables=3" in rendered
    assert "sensitive_fields=2" in rendered
    assert "abcdef12" in rendered


@pytest.mark.asyncio
async def test_schema_command_invokes_service(monkeypatch):
    calls = []

    class FakeService:
        async def ingest_current(self, source: str, force: bool = False):
            calls.append(("ingest", source, force))
            return {"source": source, "schema_hash": "hash", "table_count": 1, "column_count": 2, "sensitive_field_count": 0, "status": "fresh"}

        async def status(self, source: str):
            calls.append(("status", source, False))
            return {"source": source, "status": "fresh", "table_count": 1, "column_count": 2, "sensitive_field_count": 0}

    monkeypatch.setattr("ingestion_worker.schema_commands.SchemaService", lambda settings: FakeService())

    assert await run_schema_command("schema-ingest", source="construction_mysql", force=True, as_json=True) == 0
    assert await run_schema_command("schema-status", source="construction_mysql", force=False, as_json=False) == 0
    assert calls == [("ingest", "construction_mysql", True), ("status", "construction_mysql", False)]
