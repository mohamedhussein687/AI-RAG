from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ingestion_worker import __main__ as cli


@pytest.mark.asyncio
async def test_status_prints_table_health(monkeypatch, capsys):
    class FakeService:
        async def status(self, *, source_name, table_name):
            assert source_name == "construction_mysql"
            assert table_name is None
            return [
                SimpleNamespace(
                    source="construction_mysql",
                    table="projects",
                    tenant_id="orbit",
                    project_id="default",
                    last_sync_at=datetime(2026, 6, 22, 10, 0, tzinfo=UTC),
                    last_success_at=datetime(2026, 6, 22, 10, 1, tzinfo=UTC),
                    status="success",
                    last_error=None,
                    indexed_documents=12,
                    inactive_documents=1,
                )
            ]

    monkeypatch.setattr(cli, "RagSyncService", lambda: FakeService())

    await cli._status("construction_mysql", None, False)

    out = capsys.readouterr().out
    assert "source=construction_mysql" in out
    assert "table=projects" in out
    assert "status=success" in out
    assert "indexed=12" in out
    assert "inactive=1" in out


@pytest.mark.asyncio
async def test_status_can_print_json(monkeypatch, capsys):
    class FakeService:
        async def status(self, *, source_name, table_name):
            return [
                SimpleNamespace(
                    source="construction_mysql",
                    table="clients",
                    tenant_id="orbit",
                    project_id="default",
                    last_sync_at=None,
                    last_success_at=None,
                    status="never_run",
                    last_error="",
                    indexed_documents=0,
                    inactive_documents=0,
                )
            ]

    monkeypatch.setattr(cli, "RagSyncService", lambda: FakeService())

    await cli._status(None, None, True)

    out = capsys.readouterr().out
    assert '"table": "clients"' in out
    assert '"status": "never_run"' in out
