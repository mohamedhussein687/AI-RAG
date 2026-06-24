from __future__ import annotations

from typing import Any

from app.schema.schema_models import IDENTIFIER_PATTERN, RAW_SQL_PATTERN, QueryJoin, SchemaSnapshot, StructuredQueryPlan, ValidatedQueryPlan


READ_ONLY_OPERATIONS = {"select", "count", "aggregate"}
AGGREGATE_OPERATIONS = {"sum", "avg", "min", "max"}
ALLOWED_FILTER_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "in", "like", "is_null", "is_not_null"}


class PlanValidationError(ValueError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


def validate_plan(plan: StructuredQueryPlan, snapshot: SchemaSnapshot, *, max_rows: int = 200) -> ValidatedQueryPlan:
    if plan.raw_sql:
        raise PlanValidationError("raw SQL is not allowed")
    operation = _normalize_operation(plan.operation)
    if operation not in READ_ONLY_OPERATIONS:
        raise PlanValidationError("only read-only operations are allowed")
    if not plan.resolved_tables:
        raise PlanValidationError("query plan must include one base table")
    base_table = _validate_identifier(plan.resolved_tables[0], "table")
    table_names = [base_table]
    base = snapshot.table(base_table)
    if base is None:
        raise PlanValidationError("unknown table", details={"requested_table": base_table})
    if base.classification == "system":
        raise PlanValidationError("system table is not queryable")
    if plan.limit > max_rows:
        raise PlanValidationError("limit exceeds configured maximum", details={"limit": plan.limit, "max_rows": max_rows})

    joins: list[QueryJoin] = []
    for join in plan.joins:
        join_table = _validate_identifier(join.table, "join.table")
        table = snapshot.table(join_table)
        if table is None:
            raise PlanValidationError("unknown joined table", details={"requested_table": join_table})
        if table.classification == "system":
            raise PlanValidationError("system table is not queryable", details={"requested_table": join_table})
        _validate_join_column(join.left_column, snapshot, table_names, "join.left_column")
        _validate_column_ref(_qualify(join_table, join.right_column), snapshot, [join_table], "join.right_column")
        joins.append(join.model_copy(update={"table": join_table}))
        table_names.append(join_table)

    selected_columns = _selected_columns(plan, operation, snapshot, table_names, base_table)
    for column in selected_columns:
        _validate_column_ref(column, snapshot, table_names, "column")

    for query_filter in plan.filters:
        _validate_column_ref(query_filter.column, snapshot, table_names, "filter.column")
        if query_filter.operator not in ALLOWED_FILTER_OPERATORS:
            raise PlanValidationError("filter operator is not allowed", details={"operator": query_filter.operator})
        if query_filter.operator == "in" and not isinstance(query_filter.value, list):
            raise PlanValidationError("in filter requires a list value")
        if _value_contains_raw_sql(query_filter.value):
            raise PlanValidationError("raw SQL is not allowed in filter values")

    for order in plan.order_by:
        _validate_column_ref(order.column, snapshot, table_names, "order_by.column")

    for group_column in plan.group_by:
        _validate_column_ref(group_column, snapshot, table_names, "group_by")

    aggregate_function = None
    aggregate_column = None
    if plan.operation in AGGREGATE_OPERATIONS:
        aggregate_function = plan.operation
        aggregate_column = selected_columns[0] if selected_columns else None
        if not aggregate_column:
            raise PlanValidationError("aggregate operation requires a column")

    return ValidatedQueryPlan(
        operation=operation,
        table=base_table,
        columns=selected_columns,
        filters=plan.filters,
        joins=joins,
        group_by=plan.group_by,
        order_by=plan.order_by,
        limit=plan.limit,
        aggregate_function=aggregate_function,
        aggregate_column=aggregate_column,
    )


def _normalize_operation(operation: str) -> str:
    normalized = operation.lower().strip()
    if normalized in {"list", "details", "latest", "group_count"}:
        return "select"
    if normalized in AGGREGATE_OPERATIONS:
        return "aggregate"
    return normalized


def _selected_columns(plan: StructuredQueryPlan, operation: str, snapshot: SchemaSnapshot, table_names: list[str], base_table: str) -> list[str]:
    if operation == "count":
        return []
    if plan.columns:
        return [str(column) for column in plan.columns]
    table = snapshot.table(base_table)
    if table is None:
        return []
    return [f"{base_table}.{column.name}" for column in table.safe_columns()[:20]]


def _validate_join_column(column: str, snapshot: SchemaSnapshot, table_names: list[str], label: str) -> None:
    if "." in column:
        _validate_column_ref(column, snapshot, table_names, label)
        return
    matches = [table for table in table_names if _table_has_safe_column(snapshot, table, column)]
    if not matches:
        raise PlanValidationError("unknown join column", details={label: column})


def _validate_column_ref(ref: str, snapshot: SchemaSnapshot, table_names: list[str], label: str) -> None:
    table_name, column_name = _split_ref(ref, table_names)
    table = snapshot.table(table_name)
    if table is None:
        raise PlanValidationError("unknown table", details={label: ref})
    column = table.column(column_name)
    if column is None:
        raise PlanValidationError("unknown column", details={label: ref})
    if column.is_sensitive:
        raise PlanValidationError("sensitive column is not allowed", details={label: ref})


def _split_ref(ref: str, table_names: list[str]) -> tuple[str, str]:
    parts = str(ref).split(".", 1)
    if len(parts) == 2:
        table_name = _validate_identifier(parts[0], "table")
        column_name = _validate_identifier(parts[1], "column")
        if table_name not in table_names:
            raise PlanValidationError("column table is not part of query", details={"column": ref})
        return table_name, column_name
    column_name = _validate_identifier(ref, "column")
    if len(table_names) != 1:
        raise PlanValidationError("unqualified column is ambiguous in joined query", details={"column": ref})
    return table_names[0], column_name


def _table_has_safe_column(snapshot: SchemaSnapshot, table_name: str, column: str) -> bool:
    table = snapshot.table(table_name)
    if table is None:
        return False
    found = table.column(_validate_identifier(column, "column"))
    return bool(found and not found.is_sensitive)


def _qualify(table: str, column: str) -> str:
    return column if "." in column else f"{table}.{column}"


def _validate_identifier(value: str, label: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise PlanValidationError(f"unsafe {label} identifier", details={label: value})
    return value


def _value_contains_raw_sql(value: Any) -> bool:
    if isinstance(value, str):
        return bool(RAW_SQL_PATTERN.search(value))
    if isinstance(value, list):
        return any(_value_contains_raw_sql(item) for item in value)
    return False
