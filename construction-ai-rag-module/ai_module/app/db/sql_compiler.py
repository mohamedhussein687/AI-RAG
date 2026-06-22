from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schema.schema_models import QueryFilter, ValidatedQueryPlan


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    parameters: list[Any]
    table: str
    operation: str
    columns: list[str]


def compile_select(plan: ValidatedQueryPlan) -> CompiledQuery:
    select_clause = _select_clause(plan)
    sql = f"SELECT {select_clause} FROM {_ident(plan.table)}"
    parameters: list[Any] = []

    where_parts = []
    for query_filter in plan.filters:
        clause, values = _compile_filter(query_filter)
        where_parts.append(clause)
        parameters.extend(values)
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    if plan.group_by:
        sql += " GROUP BY " + ", ".join(_ident(column) for column in plan.group_by)

    if plan.order_by:
        order_parts = [f"{_ident(order.column)} {order.direction.upper()}" for order in plan.order_by]
        sql += " ORDER BY " + ", ".join(order_parts)

    if plan.operation != "count" and not plan.group_by:
        sql += " LIMIT %s"
        parameters.append(plan.limit)

    return CompiledQuery(sql=sql, parameters=parameters, table=plan.table, operation=plan.operation, columns=plan.columns)


def _select_clause(plan: ValidatedQueryPlan) -> str:
    if plan.operation == "count":
        return "COUNT(*) AS `count`"
    if plan.aggregate_function and plan.aggregate_column:
        return f"{plan.aggregate_function.upper()}({_ident(plan.aggregate_column)}) AS `{plan.aggregate_function}`"
    return ", ".join(_ident(column) for column in plan.columns)


def _compile_filter(query_filter: QueryFilter) -> tuple[str, list[Any]]:
    column = _ident(query_filter.column)
    operator = query_filter.operator
    if operator == "is_null":
        return f"{column} IS NULL", []
    if operator == "is_not_null":
        return f"{column} IS NOT NULL", []
    if operator == "in":
        values = list(query_filter.value)
        placeholders = ", ".join(["%s"] * len(values))
        return f"{column} IN ({placeholders})", values
    if operator == "like":
        return f"{column} LIKE %s", [f"%{query_filter.value}%"]
    return f"{column} {operator} %s", [query_filter.value]


def _ident(value: str) -> str:
    return f"`{value}`"
