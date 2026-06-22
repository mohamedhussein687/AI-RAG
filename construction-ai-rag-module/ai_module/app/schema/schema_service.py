from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings
from app.db.mysql import readonly_mysql_connection
from app.rag.document_service import DocumentService
from app.schemas import (
    AccessPolicy,
    DocumentIndexRequest,
    RagChunk,
    SchemaIngestRequest,
    SchemaIngestResponse,
    SchemaSearchRequest,
    SchemaSearchResponse,
    SchemaStatusResponse,
)
from app.schema.schema_discovery import discover_schema_from_connection
from app.schema.schema_hash import calculate_schema_hash
from app.schema.schema_ingestion import SchemaChunk, build_schema_chunks
from app.schema.schema_models import AliasCatalog, SchemaColumn as DiscoveredColumn, SchemaSnapshot, SchemaTable as DiscoveredTable, load_alias_catalog
from app.schema.schema_search import search_schema_chunks


schema_snapshots: dict[str, SchemaSnapshot] = {}
schema_aliases: dict[str, AliasCatalog] = {}
schema_chunks: dict[str, list[SchemaChunk]] = {}


class SchemaService:
    SOURCE_TYPE = "database_schema"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.documents = DocumentService(settings)

    async def ingest(self, request: SchemaIngestRequest) -> SchemaIngestResponse:
        if request.tables:
            snapshot = self._snapshot_from_request(request)
            aliases = self._load_aliases()
        else:
            result = await self.ingest_current(request.source, force=request.force)
            return SchemaIngestResponse(**result)
        return await self._ingest_snapshot(snapshot, aliases, force=request.force)

    async def ingest_current(self, source: str, *, force: bool = False) -> dict[str, Any]:
        aliases = self._load_aliases()
        async with readonly_mysql_connection(self.settings) as connection:
            snapshot = await discover_schema_from_connection(
                connection,
                source_name=source,
                database_name=self.settings.mysql_database,
                aliases=aliases,
            )
        response = await self._ingest_snapshot(snapshot, aliases, force=force)
        return response.model_dump()

    async def search(self, request: SchemaSearchRequest) -> SchemaSearchResponse:
        source = request.client_name or request.source or self.settings.schema_source_name
        chunks = schema_chunks.get(source, [])
        matches = search_schema_chunks(chunks, query=request.query, source_name=source, top_k=request.top_k)
        results = [
            RagChunk(
                chunk_id=chunk.chunk_id,
                document_id=f"schema:{chunk.source_name}:{chunk.schema_hash}:{chunk.table_name}",
                title=f"Database schema: {chunk.table_name}",
                source_type=self.SOURCE_TYPE,
                project_id=request.project_id,
                chunk_index=idx,
                text=chunk.content,
                score=float(len(matches) - idx),
            )
            for idx, chunk in enumerate(matches)
        ]
        return SchemaSearchResponse(results=results)

    async def status(self, source: str | None = None) -> SchemaStatusResponse:
        source_name = source or self.settings.schema_source_name
        snapshot = schema_snapshots.get(source_name)
        if snapshot is None:
            return SchemaStatusResponse(source=source_name, database_name=self.settings.mysql_database or None, status="missing")
        aliases = self._load_aliases()
        current_hash = calculate_schema_hash(snapshot, aliases)
        stale = current_hash != snapshot.schema_hash or aliases.alias_hash != snapshot.alias_hash
        return SchemaStatusResponse(
            source=source_name,
            database_name=snapshot.database_name,
            schema_hash=snapshot.schema_hash,
            alias_hash=snapshot.alias_hash,
            table_count=snapshot.table_count,
            column_count=snapshot.column_count,
            sensitive_field_count=snapshot.sensitive_field_count,
            status="stale" if stale else snapshot.status,
            generated_at=snapshot.generated_at.isoformat(),
            stale_reason="schema_or_alias_hash_changed" if stale else None,
        )

    async def _ingest_snapshot(self, snapshot: SchemaSnapshot, aliases: AliasCatalog, *, force: bool = False) -> SchemaIngestResponse:
        existing = schema_snapshots.get(snapshot.source_name)
        if existing and existing.schema_hash == snapshot.schema_hash and existing.alias_hash == snapshot.alias_hash and not force:
            chunks = schema_chunks.get(snapshot.source_name, [])
            return SchemaIngestResponse(
                source=snapshot.source_name,
                client_name=snapshot.source_name,
                schema_hash=snapshot.schema_hash,
                alias_hash=snapshot.alias_hash,
                table_count=snapshot.table_count,
                column_count=snapshot.column_count,
                sensitive_field_count=snapshot.sensitive_field_count,
                tables_indexed=snapshot.table_count,
                chunks_indexed=len(chunks),
                status="fresh",
            )

        chunks = build_schema_chunks(snapshot, aliases)
        indexed_chunks = 0
        for chunk in chunks:
            response = await self.documents.index(
                DocumentIndexRequest(
                    tenant_id=snapshot.source_name,
                    project_id=snapshot.source_name,
                    title=f"Database schema: {snapshot.source_name}.{chunk.table_name}",
                    source_type=self.SOURCE_TYPE,
                    content=chunk.content,
                    access_policy=AccessPolicy(permissions=["live-data.read", "schema.read"]),
                    metadata={
                        "source_identity": f"schema:{snapshot.source_name}:{snapshot.schema_hash}:{chunk.table_name}",
                        "client_name": snapshot.source_name,
                        "schema_hash": snapshot.schema_hash,
                        "schema_table": chunk.table_name,
                        "table_category": chunk.metadata.get("classification"),
                        "enabled_for_planning": chunk.metadata.get("classification") != "system",
                        "version": snapshot.schema_hash,
                        "is_active": True,
                    },
                )
            )
            indexed_chunks += response.chunks_indexed
        schema_snapshots[snapshot.source_name] = snapshot
        schema_aliases[snapshot.source_name] = aliases
        schema_chunks[snapshot.source_name] = chunks
        return SchemaIngestResponse(
            source=snapshot.source_name,
            client_name=snapshot.source_name,
            schema_hash=snapshot.schema_hash,
            alias_hash=snapshot.alias_hash,
            table_count=snapshot.table_count,
            column_count=snapshot.column_count,
            sensitive_field_count=snapshot.sensitive_field_count,
            tables_indexed=snapshot.table_count,
            chunks_indexed=indexed_chunks,
            status="fresh",
        )

    def _snapshot_from_request(self, request: SchemaIngestRequest) -> SchemaSnapshot:
        tables = []
        for table in request.tables:
            columns = [
                DiscoveredColumn(
                    name=column.name,
                    data_type=column.type or column.columnType or "",
                    nullable=True if column.nullable is None else column.nullable,
                    is_primary_key=bool(column.primaryKey),
                    is_sensitive=column.sensitive,
                    enum_like_values=[str(value) for value in column.knownValues] if isinstance(column.knownValues, list) else list(column.knownValues.keys()),
                    safe_sample_values=[str(value) for value in column.knownValues.values()] if isinstance(column.knownValues, dict) else [str(value) for value in column.knownValues],
                    semantic_description=column.description,
                )
                for column in table.columns
            ]
            tables.append(
                DiscoveredTable(
                    name=table.name,
                    classification=_category(table.category),
                    approximate_row_count=table.approxRows,
                    primary_key_columns=table.primaryKey,
                    business_description=table.description,
                    columns=columns,
                )
            )
        aliases = self._load_aliases()
        snapshot = SchemaSnapshot(
            source_name=request.client_name or request.source,
            database_name=self.settings.mysql_database or request.client_name or request.source,
            schema_hash=request.schema_hash or "pending",
            alias_hash=aliases.alias_hash,
            tables=tables,
        )
        if not request.schema_hash:
            snapshot = snapshot.model_copy(update={"schema_hash": calculate_schema_hash(snapshot, aliases)})
        return snapshot

    def _load_aliases(self) -> AliasCatalog:
        return load_alias_catalog(_resolve_path(self.settings.schema_aliases_path))


def _category(value: str) -> str:
    return value if value in {"business", "cms_content", "system", "unknown"} else "unknown"


def _resolve_path(path: str) -> Path:
    raw = Path(path)
    if raw.exists() or raw.is_absolute():
        return raw
    module_root = Path(__file__).resolve().parents[2]
    candidate = module_root / path
    if candidate.exists():
        return candidate
    return raw
