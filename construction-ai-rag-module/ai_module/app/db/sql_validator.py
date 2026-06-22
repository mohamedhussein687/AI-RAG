from __future__ import annotations

from typing import Any

from app.schema.schema_models import IDENTIFIER_PATTERN, RAW_SQL_PATTERN, SchemaSnapshot, StructuredQueryPlan, ValidatedQueryPlan


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
        raise PlanValidationError("query plan must include one resolved table")
    if len(plan.resolved_tables) != 1:
        raise PlanValidationError("only single-table plans are supported in this phase")
    table_name = _validate_identifier(plan.resolved_tables[0], "table")
    table = snapshot.table(table_name)
    if table is None:
        raise PlanValidationError("unknown table", details={"requested_table": table_name})
    if table.classification == "system":
        raise PlanValidationError("system table is not queryable")

    if plan.limit > max_rows:
        raise PlanValidationError("limit exceeds configured maximum", details={"limit": plan.limit, "max_rows": max_rows})

    safe_column_names = {column.name for column in table.safe_columns()}
    all_column_names = {column.name for column in table.columns}
    selected_columns = _selected_columns(plan, operation, safe_column_names)
    for column in selected_columns:
        _validate_column(column, all_column_names, safe_column_names)

    for query_filter in plan.filters:
        _validate_column(query_filter.column, all_column_names, safe_column_names)
        if query_filter.operator not in ALLOWED_FILTER_OPERATORS:
            raise PlanValidationError("filter operator is not allowed", details={"operator": query_filter.operator})
        if query_filter.operator == "in" and not isinstance(query_filter.value, list):
            raise PlanValidationError("in filter requires a list value")
        if _value_contains_raw_sql(query_filter.value):
            raise PlanValidationError("raw SQL is not allowed in filter values")

    for order in plan.order_by:
        _validate_column(order.column, all_column_names, safe_column_names)

    for group_column in plan.group_by:
        _validate_column(group_column, all_column_names, safe_column_names)

    aggregate_function = None
    aggregate_column = None
    if plan.operation in AGGREGATE_OPERATIONS:
        aggregate_function = plan.operation
        aggregate_column = selected_columns[0] if selected_columns else None
        if not aggregate_column:
            raise PlanValidationError("aggregate operation requires a column")

    return ValidatedQueryPlan(
        operation=operation,
        table=table_name,
        columns=selected_columns,
        filters=plan.filters,
        group_by=plan.group_by,
        order_by=plan.order_by,
        limit=plan.limit,
        aggregate_function=aggregate_function,
        aggregate_column=aggregate_column,
    )


def _normalize_operation(operation: str) -> str:
    normalized = operation.lower().strip()
    if normalized in {"list", "details", "latest"}:
        return "select"
    if normalized in AGGREGATE_OPERATIONS:
        return "aggregate"
    return normalized


def _selected_columns(plan: StructuredQueryPlan, operation: str, safe_column_names: set[str]) -> list[str]:
    if operation == "count":
        return []
    if plan.columns:
        return [_validate_identifier(column, "column") for column in plan.columns]
    return sorted(safe_column_names)[:20]


def _validate_column(column: str, all_column_names: set[str], safe_column_names: set[str]) -> None:
    column = _validate_identifier(column, "column")
    if column not in all_column_names:
        raise PlanValidationError("unknown column", details={"column": column})
    if column not in safe_column_names:
        raise PlanValidationError("sensitive column is not allowed", details={"column": column})


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
