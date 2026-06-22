from __future__ import annotations

import pytest

from app.schema.schema_discovery import discover_schema_from_connection


class FakeCursor:
    def __init__(self, responses):
        self.responses = responses
        self.executed: list[tuple[str, list | None]] = []
        self._rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        lowered = " ".join(sql.lower().split())
        for key, rows in self.responses.items():
            if key in lowered:
                self._rows = rows
                return
        self._rows = []

    async def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, responses):
        self.cursor_obj = FakeCursor(responses)

    def cursor(self):
        return self.cursor_obj


@pytest.mark.asyncio
async def test_schema_discovery_reads_tables_columns_keys_indexes_foreign_keys_enums_and_counts():
    conn = FakeConnection(
        {
            "from information_schema.tables": [
                {"table_name": "projects", "table_comment": "Construction projects", "table_rows": 12},
                {"table_name": "about_us", "table_comment": "CMS about page", "table_rows": 1},
            ],
            "from information_schema.columns": [
                {
                    "table_name": "projects",
                    "column_name": "id",
                    "data_type": "bigint",
                    "column_type": "bigint unsigned",
                    "is_nullable": "NO",
                    "column_default": None,
                    "column_comment": "Primary key",
                    "column_key": "PRI",
                },
                {
                    "table_name": "projects",
                    "column_name": "project_status",
                    "data_type": "enum",
                    "column_type": "enum('waiting','active','completed')",
                    "is_nullable": "YES",
                    "column_default": None,
                    "column_comment": "Project state",
                    "column_key": "MUL",
                },
                {
                    "table_name": "projects",
                    "column_name": "client_id",
                    "data_type": "bigint",
                    "column_type": "bigint unsigned",
                    "is_nullable": "YES",
                    "column_default": None,
                    "column_comment": "",
                    "column_key": "MUL",
                },
                {
                    "table_name": "projects",
                    "column_name": "password",
                    "data_type": "varchar",
                    "column_type": "varchar(255)",
                    "is_nullable": "YES",
                    "column_default": None,
                    "column_comment": "",
                    "column_key": "",
                },
            ],
            "from information_schema.statistics": [
                {"table_name": "projects", "index_name": "PRIMARY", "column_name": "id", "non_unique": 0, "seq_in_index": 1},
                {"table_name": "projects", "index_name": "idx_projects_status", "column_name": "project_status", "non_unique": 1, "seq_in_index": 1},
            ],
            "from information_schema.key_column_usage": [
                {
                    "table_name": "projects",
                    "column_name": "client_id",
                    "referenced_table_name": "clients",
                    "referenced_column_name": "id",
                    "constraint_name": "fk_projects_client",
                }
            ],
            "select `project_status`": [{"project_status": "waiting"}, {"project_status": "active"}],
            "select `id`": [{"id": 1}, {"id": 2}],
            "select `client_id`": [{"client_id": 10}],
        }
    )

    snapshot = await discover_schema_from_connection(conn, source_name="construction_mysql", database_name="construction_ai_dev")

    assert snapshot.database_name == "construction_ai_dev"
    assert snapshot.table_count == 2
    projects = snapshot.table("projects")
    assert projects is not None
    assert projects.classification == "business"
    assert projects.primary_key_columns == ["id"]
    assert projects.approximate_row_count == 12
    assert projects.column("project_status").enum_like_values == ["waiting", "active", "completed"]
    assert projects.column("project_status").safe_sample_values == ["waiting", "active"]
    assert projects.column("client_id").is_foreign_key is True
    assert projects.foreign_keys[0].referenced_table == "clients"
    assert projects.indexes[1].columns == ["project_status"]
    assert snapshot.table("about_us").classification == "cms_content"


@pytest.mark.asyncio
async def test_schema_discovery_excludes_sensitive_samples():
    conn = FakeConnection(
        {
            "from information_schema.tables": [{"table_name": "users", "table_comment": "", "table_rows": 1}],
            "from information_schema.columns": [
                {
                    "table_name": "users",
                    "column_name": "password",
                    "data_type": "varchar",
                    "column_type": "varchar(255)",
                    "is_nullable": "YES",
                    "column_default": None,
                    "column_comment": "",
                    "column_key": "",
                },
                {
                    "table_name": "users",
                    "column_name": "name",
                    "data_type": "varchar",
                    "column_type": "varchar(255)",
                    "is_nullable": "YES",
                    "column_default": None,
                    "column_comment": "",
                    "column_key": "",
                },
            ],
            "from information_schema.statistics": [],
            "from information_schema.key_column_usage": [],
            "select `name`": [{"name": "Basma"}],
        }
    )

    snapshot = await discover_schema_from_connection(conn, source_name="construction_mysql", database_name="construction_ai_dev")
    users = snapshot.table("users")

    assert users.column("password").is_sensitive is True
    assert users.column("password").safe_sample_values == []
    assert users.safe_sample_summary == {"name": ["Basma"]}
    executed_sql = "\n".join(sql for sql, _ in conn.cursor_obj.executed)
    assert "select `password`" not in executed_sql.lower()
