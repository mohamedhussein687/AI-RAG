from __future__ import annotations

import logging
from typing import Any

from app.agent.decision_service import DecisionService
from app.agent.final_answer_service import FinalAnswerService
from app.config import Settings
from app.db.mysql import readonly_mysql_connection
from app.db.sql_compiler import compile_select
from app.db.sql_executor import QueryExecutor
from app.db.sql_validator import PlanValidationError, validate_plan
from app.schema.schema_models import QueryFilter, QueryOrderBy, SchemaColumn, SchemaSnapshot, SchemaTable, StructuredQueryPlan
from app.schemas import (
    AgentDecideRequest,
    AgentDecision,
    AgentFinalRequest,
    AgentFinalResponse,
    DatabaseAwareChatResponse,
    Display,
    ExecutedQuerySummary,
    ToolCallsDecision,
    ToolResult,
)

log = logging.getLogger(__name__)


class DatabaseChatService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.decision_service = DecisionService(settings)
        self.final_answer_service = FinalAnswerService(settings)

    async def chat(self, request: AgentDecideRequest) -> DatabaseAwareChatResponse:
        decision = await self.decision_service.decide(request)
        if getattr(decision, "type", None) != "tool_calls":
            return self._decision_response(decision)
        assert isinstance(decision, ToolCallsDecision)
        tool_results: list[ToolResult] = []
        for call in decision.tool_calls[: request.rules.max_tool_calls]:
            try:
                snapshot = self._schema_snapshot(request)
                result = await self._execute_tool_call(call.plan.model_dump(), snapshot, request)
            except (PlanValidationError, ValueError) as exc:
                details = getattr(exc, "details", {}) if isinstance(getattr(exc, "details", {}), dict) else {}
                result = {
                    "operation": "validation_error",
                    "error_code": "validation_error",
                    "message": str(exc),
                    "requested_table": details.get("requested_table", call.plan.table),
                    "details": details,
                }
            tool_results.append(ToolResult(tool_call_id=call.id, tool="database_query", result=result))

        final = await self.final_answer_service.final(
            AgentFinalRequest(
                conversation_id=request.conversation_id,
                message=request.message,
                locale=request.locale,
                conversation_history=request.conversation_history,
                tool_results=tool_results,
                local_rag_results=decision.local_rag_results,
                final_answer_instruction=decision.final_answer_instruction,
            )
        )
        summary = self._summary_from_results(tool_results)
        return DatabaseAwareChatResponse(
            answer=final.answer,
            route=decision.route,
            display=final.display,
            executed_query_summary=summary,
            sources=final.sources,
        )

    async def _execute_tool_call(self, raw_plan: dict[str, Any], snapshot: SchemaSnapshot, request: AgentDecideRequest) -> dict[str, Any]:
        structured = self._structured_plan(raw_plan)
        validated = validate_plan(structured, snapshot, max_rows=min(request.rules.max_rows, self.settings.mysql_max_rows))
        query = compile_select(validated)
        log.info(
            "database_chat_query route=database_query operation=%s selected_table=%s columns=%s filters=%s limit=%s sql_template=%s",
            validated.operation,
            validated.table,
            validated.columns,
            len(validated.filters),
            validated.limit,
            query.sql,
        )
        async with readonly_mysql_connection(self.settings) as connection:
            execution = await QueryExecutor(
                connection,
                max_rows=min(request.rules.max_rows, self.settings.mysql_max_rows),
                timeout_seconds=self.settings.mysql_query_timeout_seconds,
            ).execute(query)
        result: dict[str, Any] = {
            "operation": validated.operation,
            "table": validated.table,
            "rows": execution.rows,
            "summary": {
                **execution.summary,
                "filters": [
                    {"column": item.column, "operator": item.operator, "value": item.value}
                    for item in validated.filters
                    if item.value not in (None, "")
                ],
            },
        }
        if validated.operation == "count":
            result["count"] = self._first_scalar(execution.rows, "count", default=0)
        if validated.aggregate_function:
            result[validated.aggregate_function] = self._first_scalar(execution.rows, validated.aggregate_function, default=0)
            result["column"] = validated.aggregate_column
        return result

    def _structured_plan(self, raw_plan: dict[str, Any]) -> StructuredQueryPlan:
        operation = str(raw_plan.get("operation") or "")
        filters = [self._filter(item) for item in raw_plan.get("filters") or []]
        order_by = [self._order_by(raw_plan["order_by"])] if isinstance(raw_plan.get("order_by"), dict) else []
        columns = [str(item) for item in (raw_plan.get("columns") or raw_plan.get("fields") or []) if item]
        column = raw_plan.get("column")
        if operation in {"sum", "avg", "min", "max"} and column and not columns:
            columns = [str(column)]
        return StructuredQueryPlan(
            route="database_query",
            operation=operation,
            logical_entities=[str(item) for item in raw_plan.get("entities") or raw_plan.get("logical_entities") or []],
            resolved_tables=[str(raw_plan.get("table") or raw_plan.get("resolved_tables", [""])[0])],
            columns=columns,
            filters=filters,
            group_by=[str(raw_plan["group_by"])] if raw_plan.get("group_by") else [],
            order_by=order_by,
            limit=int(raw_plan.get("limit") or self.settings.mysql_max_rows),
        )

    @staticmethod
    def _filter(item: Any) -> QueryFilter:
        if not isinstance(item, dict):
            raise PlanValidationError("filter must be an object")
        operator = _operator(str(item.get("operator") or "="))
        return QueryFilter(column=str(item.get("column") or item.get("field") or ""), operator=operator, value=item.get("value"))

    @staticmethod
    def _order_by(item: dict[str, Any]) -> QueryOrderBy:
        return QueryOrderBy(column=str(item.get("column") or item.get("field") or ""), direction=str(item.get("direction") or "asc").lower())

    def _schema_snapshot(self, request: AgentDecideRequest) -> SchemaSnapshot:
        catalog = request.semantic_catalog or {}
        if isinstance(catalog.get("schema_snapshot"), dict):
            return SchemaSnapshot.model_validate(catalog["schema_snapshot"])
        tables = catalog.get("tables") if isinstance(catalog.get("tables"), list) else []
        if not tables and request.allowed_schema.tables:
            tables = [
                {
                    "name": table.name,
                    "columns": [{"name": column, "type": "unknown"} for column in table.columns],
                }
                for table in request.allowed_schema.tables
            ]
        if not tables:
            raise PlanValidationError("schema metadata is unavailable")
        return SchemaSnapshot(
            source_name=str(catalog.get("source_name") or catalog.get("client_name") or "construction_mysql"),
            database_name=str(catalog.get("database_name") or self.settings.mysql_database or "unknown"),
            schema_hash=str(catalog.get("schema_hash") or "request-catalog"),
            alias_hash=catalog.get("alias_hash"),
            tables=[self._schema_table(table) for table in tables if isinstance(table, dict)],
        )

    def _schema_table(self, table: dict[str, Any]) -> SchemaTable:
        classification = str(table.get("classification") or table.get("category") or "business")
        if classification not in {"business", "cms_content", "system", "unknown"}:
            classification = "unknown"
        columns = []
        for column in table.get("columns") or []:
            if isinstance(column, str):
                columns.append(SchemaColumn(name=column, data_type="unknown"))
            elif isinstance(column, dict):
                columns.append(
                    SchemaColumn(
                        name=str(column.get("name") or ""),
                        data_type=str(column.get("data_type") or column.get("type") or column.get("columnType") or "unknown"),
                        nullable=bool(column.get("nullable", True)),
                        is_primary_key=bool(column.get("is_primary_key") or column.get("primaryKey") or False),
                        is_sensitive=bool(column.get("is_sensitive") or column.get("sensitive") or False),
                        enum_like_values=[str(item) for item in column.get("enum_like_values") or column.get("knownValues") or [] if not isinstance(item, dict)],
                        semantic_description=column.get("semantic_description") or column.get("description"),
                    )
                )
        return SchemaTable(
            name=str(table.get("name") or ""),
            classification=classification,  # type: ignore[arg-type]
            approximate_row_count=table.get("approximate_row_count") or table.get("approxRows"),
            primary_key_columns=[str(item) for item in table.get("primary_key_columns") or table.get("primaryKey") or []],
            columns=columns,
        )

    def _decision_response(self, decision: AgentDecision) -> DatabaseAwareChatResponse:
        answer = getattr(decision, "answer", None) or getattr(decision, "question", None) or "لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."
        display = getattr(decision, "display", Display(type="text"))
        sources = getattr(decision, "sources", [])
        route = getattr(decision, "route", "unsupported")
        return DatabaseAwareChatResponse(answer=answer, route=route, display=display, sources=sources)

    @staticmethod
    def _summary_from_results(results: list[ToolResult]) -> ExecutedQuerySummary | None:
        for item in results:
            payload = item.result
            if not isinstance(payload, dict):
                continue
            summary = payload.get("summary")
            if isinstance(summary, dict):
                return ExecutedQuerySummary(
                    operation=str(summary.get("operation") or payload.get("operation") or ""),
                    tables=[str(summary.get("table") or payload.get("table"))] if (summary.get("table") or payload.get("table")) else [],
                    columns=[str(column) for column in summary.get("columns") or []],
                    row_count=int(summary.get("row_count") or 0),
                    truncated=bool(summary.get("truncated", False)),
                )
        return None

    @staticmethod
    def _first_scalar(rows: list[dict[str, Any]], key: str, *, default: Any) -> Any:
        if not rows:
            return default
        return rows[0].get(key, default)


def _operator(value: str):
    aliases = {
        "eq": "=",
        "=": "=",
        "==": "=",
        "ne": "!=",
        "!=": "!=",
        "<>": "!=",
        "gt": ">",
        ">": ">",
        "gte": ">=",
        ">=": ">=",
        "lt": "<",
        "<": "<",
        "lte": "<=",
        "<=": "<=",
        "contains": "like",
        "like": "like",
        "in": "in",
        "is_null": "is_null",
        "is_not_null": "is_not_null",
    }
    return aliases.get(value.strip().lower(), value.strip().lower())
