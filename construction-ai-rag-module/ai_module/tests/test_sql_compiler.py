from app.db.sql_compiler import compile_select
from app.db.sql_validator import validate_plan
from app.schema.schema_models import SchemaColumn, SchemaSnapshot, SchemaTable, StructuredQueryPlan


def snapshot() -> SchemaSnapshot:
    return SchemaSnapshot(
        source_name="construction_mysql",
        database_name="construction_ai_dev",
        schema_hash="abc",
        tables=[
            SchemaTable(
                name="projects",
                classification="business",
                columns=[
                    SchemaColumn(name="id", data_type="int", is_primary_key=True),
                    SchemaColumn(name="name", data_type="varchar"),
                    SchemaColumn(name="project_status", data_type="varchar"),
                    SchemaColumn(name="created_at", data_type="datetime"),
                ],
                primary_key_columns=["id"],
            ),
            SchemaTable(
                name="invoices",
                classification="business",
                columns=[
                    SchemaColumn(name="id", data_type="int", is_primary_key=True),
                    SchemaColumn(name="project_id", data_type="int"),
                    SchemaColumn(name="total", data_type="decimal"),
                    SchemaColumn(name="paid", data_type="tinyint"),
                ],
                primary_key_columns=["id"],
            )
        ],
    )


def test_compile_select_uses_placeholders_for_filter_values() -> None:
    plan = StructuredQueryPlan(
        route="database_query",
        operation="select",
        resolved_tables=["projects"],
        columns=["name", "project_status"],
        filters=[{"column": "project_status", "operator": "=", "value": "waiting"}],
        order_by=[{"column": "created_at", "direction": "desc"}],
        limit=10,
    )
    validated = validate_plan(plan, snapshot())

    compiled = compile_select(validated)

    assert compiled.sql == "SELECT `name`, `project_status` FROM `projects` WHERE `project_status` = %s ORDER BY `created_at` DESC LIMIT %s"
    assert compiled.parameters == ["waiting", 10]


def test_compile_count_generates_bounded_count_query() -> None:
    plan = StructuredQueryPlan(
        route="database_query",
        operation="count",
        resolved_tables=["projects"],
        filters=[{"column": "project_status", "operator": "in", "value": ["waiting", "active"]}],
    )
    validated = validate_plan(plan, snapshot())

    compiled = compile_select(validated)

    assert compiled.sql == "SELECT COUNT(*) AS `count` FROM `projects` WHERE `project_status` IN (%s, %s)"
    assert compiled.parameters == ["waiting", "active"]


def test_compile_like_wraps_value_without_string_interpolation() -> None:
    plan = StructuredQueryPlan(
        route="database_query",
        operation="select",
        resolved_tables=["projects"],
        columns=["name"],
        filters=[{"column": "name", "operator": "like", "value": "test60"}],
        limit=5,
    )
    validated = validate_plan(plan, snapshot())

    compiled = compile_select(validated)

    assert "`name` LIKE %s" in compiled.sql
    assert compiled.parameters == ["%test60%", 5]


def test_compile_join_plan_qualifies_joined_columns() -> None:
    plan = StructuredQueryPlan(
        route="database_query",
        operation="select",
        resolved_tables=["projects"],
        joins=[{"table": "invoices", "left_column": "id", "right_column": "project_id", "type": "left"}],
        columns=["projects.name", "invoices.total"],
        filters=[{"column": "invoices.paid", "operator": "=", "value": 1}],
        limit=10,
    )
    validated = validate_plan(plan, snapshot())

    compiled = compile_select(validated)

    assert "LEFT JOIN `invoices` ON `projects`.`id` = `invoices`.`project_id`" in compiled.sql
    assert "`projects`.`name` AS `projects__name`" in compiled.sql
    assert "`invoices`.`total` AS `invoices__total`" in compiled.sql
    assert compiled.parameters == [1, 10]
