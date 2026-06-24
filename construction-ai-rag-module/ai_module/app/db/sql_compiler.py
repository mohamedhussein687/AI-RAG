from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schema.schema_models import QueryFilter, QueryJoin, ValidatedQueryPlan


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    parameters: list[Any]
    table: str
    operation: str
    columns: list[str]


def compile_select(plan: ValidatedQueryPlan) -> CompiledQuery:
    qualify = bool(plan.joins)
    select_clause = _select_clause(plan, qualify=qualify)
    sql = f"SELECT {select_clause} FROM {_ident(plan.table)}"
    for join in plan.joins:
        join_type = "LEFT JOIN" if join.type == "left" else "INNER JOIN"
        sql += f" {join_type} {_ident(join.table)} ON {_join_left(plan, join)} = {_column_ref(_qualify(join.table, join.right_column, plan.table), plan.table, qualify=True)}"
    parameters: list[Any] = []

    where_parts = []
    for query_filter in plan.filters:
        clause, values = _compile_filter(query_filter, plan.table, qualify=qualify)
        where_parts.append(clause)
        parameters.extend(values)
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    if plan.group_by:
        sql += " GROUP BY " + ", ".join(_column_ref(column, plan.table, qualify=qualify) for column in plan.group_by)

    if plan.order_by:
        order_parts = [f"{_column_ref(order.column, plan.table, qualify=qualify)} {order.direction.upper()}" for order in plan.order_by]
        sql += " ORDER BY " + ", ".join(order_parts)

    if plan.operation != "count" and not plan.group_by:
        sql += " LIMIT %s"
        parameters.append(plan.limit)

    return CompiledQuery(sql=sql, parameters=parameters, table=plan.table, operation=plan.operation, columns=plan.columns)


def _select_clause(plan: ValidatedQueryPlan, *, qualify: bool) -> str:
    if plan.operation == "count":
        return "COUNT(*) AS `count`"
    if plan.aggregate_function and plan.aggregate_column:
        return f"{plan.aggregate_function.upper()}({_column_ref(plan.aggregate_column, plan.table, qualify=qualify)}) AS `{plan.aggregate_function}`"
    if not qualify:
        return ", ".join(_ident(column) for column in plan.columns)
    return ", ".join(f"{_column_ref(column, plan.table, qualify=True)} AS {_alias(column)}" for column in plan.columns)


def _compile_filter(query_filter: QueryFilter, base_table: str, *, qualify: bool) -> tuple[str, list[Any]]:
    column = _column_ref(query_filter.column, base_table, qualify=qualify)
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


def _join_left(plan: ValidatedQueryPlan, join: QueryJoin) -> str:
    return _column_ref(_qualify(plan.table, join.left_column, plan.table), plan.table, qualify=True)


def _qualify(table: str, column: str, base_table: str) -> str:
    if "." in column:
        return column
    return f"{table}.{column}" if table else f"{base_table}.{column}"


def _column_ref(value: str, base_table: str, *, qualify: bool = False) -> str:
    if "." in value:
        table, column = value.split(".", 1)
        return f"{_ident(table)}.{_ident(column)}" if qualify else _ident(column)
    return f"{_ident(base_table)}.{_ident(value)}" if qualify else _ident(value)


def _ident(value: str) -> str:
    return f"`{value}`"


def _alias(value: str) -> str:
    return _ident(value.replace(".", "__"))
