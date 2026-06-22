import pytest

from app.db.sql_validator import PlanValidationError, validate_plan
from app.schema.schema_models import SchemaColumn, SchemaSnapshot, SchemaTable, StructuredQueryPlan


def snapshot() -> SchemaSnapshot:
    return SchemaSnapshot(
        source_name="construction_mysql",
        database_name="construction_ai_dev",
        schema_hash="abc",
        alias_hash="def",
        tables=[
            SchemaTable(
                name="users",
                classification="business",
                columns=[
                    SchemaColumn(name="id", data_type="int", is_primary_key=True),
                    SchemaColumn(name="name", data_type="varchar"),
                    SchemaColumn(name="email", data_type="varchar"),
                    SchemaColumn(name="password", data_type="varchar", is_sensitive=True),
                    SchemaColumn(name="created_at", data_type="datetime"),
                ],
                primary_key_columns=["id"],
            )
        ],
    )


def test_validate_accepts_safe_select_plan() -> None:
    plan = StructuredQueryPlan(
        route="database_query",
        operation="select",
        resolved_tables=["users"],
        columns=["name", "email"],
        filters=[{"column": "name", "operator": "like", "value": "Ayman"}],
        order_by=[{"column": "created_at", "direction": "desc"}],
        limit=20,
    )

    validated = validate_plan(plan, snapshot())

    assert validated.table == "users"
    assert validated.columns == ["name", "email"]
    assert validated.limit == 20


def test_validate_rejects_unknown_table() -> None:
    plan = StructuredQueryPlan(route="database_query", operation="select", resolved_tables=["accounts"], columns=["name"])

    with pytest.raises(PlanValidationError, match="unknown table"):
        validate_plan(plan, snapshot())


def test_validate_rejects_sensitive_column() -> None:
    plan = StructuredQueryPlan(route="database_query", operation="select", resolved_tables=["users"], columns=["password"])

    with pytest.raises(PlanValidationError, match="sensitive column"):
        validate_plan(plan, snapshot())


def test_validate_rejects_raw_sql_payload() -> None:
    plan = StructuredQueryPlan(route="database_query", operation="select", resolved_tables=["users"], columns=["name"], raw_sql="select * from users")

    with pytest.raises(PlanValidationError, match="raw SQL"):
        validate_plan(plan, snapshot())


def test_validate_rejects_write_operation() -> None:
    plan = StructuredQueryPlan(route="database_query", operation="delete", resolved_tables=["users"], columns=["id"])

    with pytest.raises(PlanValidationError, match="read-only"):
        validate_plan(plan, snapshot())


def test_validate_enforces_max_limit() -> None:
    plan = StructuredQueryPlan(route="database_query", operation="select", resolved_tables=["users"], columns=["name"], limit=5000)

    with pytest.raises(PlanValidationError, match="limit"):
        validate_plan(plan, snapshot(), max_rows=100)
