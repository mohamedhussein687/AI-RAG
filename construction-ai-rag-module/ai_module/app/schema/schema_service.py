import json
from typing import Any

from app.config import Settings
from app.rag.document_service import DocumentService
from app.rag.retrieval_service import RetrievalService
from app.schemas import (
    AccessPolicy,
    DocumentIndexRequest,
    RagFilters,
    RagSearchRequest,
    SchemaIngestRequest,
    SchemaIngestResponse,
    SchemaSearchRequest,
    SchemaSearchResponse,
    UserContext,
)


class SchemaService:
    SOURCE_TYPE = "database_schema"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.documents = DocumentService(settings)
        self.retrieval = RetrievalService(settings)

    async def ingest(self, request: SchemaIngestRequest) -> SchemaIngestResponse:
        tables_indexed = 0
        chunks_indexed = 0
        for table in request.tables:
            content = self._table_document(request, table.model_dump())
            response = await self.documents.index(
                DocumentIndexRequest(
                    tenant_id=request.tenant_id,
                    project_id=request.project_id,
                    title=f"Database schema: {request.client_name}.{table.name}",
                    source_type=self.SOURCE_TYPE,
                    content=content,
                    access_policy=AccessPolicy(permissions=["live-data.read", "schema.read"]),
                    metadata={
                        "source_identity": f"schema:{request.client_name}:{request.schema_hash}:{table.name}",
                        "client_name": request.client_name,
                        "schema_hash": request.schema_hash,
                        "schema_table": table.name,
                        "table_category": table.category,
                        "enabled_for_planning": table.enabledForPlanning,
                        "version": request.schema_hash,
                    },
                )
            )
            tables_indexed += 1
            chunks_indexed += response.chunks_indexed
        return SchemaIngestResponse(
            client_name=request.client_name,
            schema_hash=request.schema_hash,
            tables_indexed=tables_indexed,
            chunks_indexed=chunks_indexed,
        )

    async def search(self, request: SchemaSearchRequest) -> SchemaSearchResponse:
        user_context = UserContext(
            id=f"schema-search:{request.client_name or request.tenant_id}",
            tenant_id=request.tenant_id,
            project_ids=[request.project_id] if request.project_id else [],
            roles=["schema-reader"],
            permissions=["live-data.read", "schema.read"],
        )
        search = RagSearchRequest(
            query=request.query,
            user_context=user_context,
            top_k=request.top_k,
            filters=RagFilters(document_types=[self.SOURCE_TYPE], project_id=request.project_id),
        )
        results = (await self.retrieval.search(search)).results
        return SchemaSearchResponse(results=results)

    def _table_document(self, request: SchemaIngestRequest, table: dict[str, Any]) -> str:
        columns = table.get("columns") or []
        public_columns = [c for c in columns if not c.get("sensitive")]
        sensitive_columns = [str(c.get("name")) for c in columns if c.get("sensitive")]
        lines = [
            "Database schema document for Qwen query planning.",
            f"Client: {request.client_name}",
            f"Tenant: {request.tenant_id}",
            f"Project: {request.project_id or ''}",
            f"Schema hash: {request.schema_hash}",
            f"Table: {table.get('name')}",
            f"Category: {table.get('category', 'business')}",
            f"Enabled for planning: {table.get('enabledForPlanning', True)}",
            f"Approximate rows: {table.get('approxRows')}",
            f"Description: {table.get('description') or table.get('name')}",
            "",
            "Columns:",
        ]
        for column in public_columns:
            known_values = column.get("knownValues") or {}
            lines.append(
                "- "
                + json.dumps(
                    {
                        "name": column.get("name"),
                        "type": column.get("type") or column.get("columnType"),
                        "nullable": column.get("nullable"),
                        "primary_key": column.get("primaryKey"),
                        "description": column.get("description"),
                        "known_values": known_values,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        if sensitive_columns:
            lines.append("")
            lines.append("Sensitive columns excluded from query plans: " + ", ".join(sorted(sensitive_columns)))
        lines.extend(
            [
                "",
                "Primary key: " + json.dumps(table.get("primaryKey") or [], ensure_ascii=False),
                "Foreign keys: " + json.dumps(table.get("foreignKeys") or [], ensure_ascii=False, sort_keys=True),
                "Indexes: " + json.dumps(table.get("indexes") or [], ensure_ascii=False, sort_keys=True),
                "",
                "Planning rules: use this table only when it matches the user's business question. "
                "Never use sensitive columns. Never output SQL. Return only a structured database_plan.",
            ]
        )
        return "\n".join(lines)
