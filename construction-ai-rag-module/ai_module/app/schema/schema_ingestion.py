from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.schema.schema_models import AliasCatalog, SchemaSnapshot, stable_json_hash


@dataclass(frozen=True)
class SchemaChunk:
    chunk_id: str
    source_name: str
    schema_hash: str
    table_name: str
    column_names: list[str]
    content: str
    metadata: dict[str, Any]
    indexed_at: datetime


def build_schema_chunks(snapshot: SchemaSnapshot, aliases: AliasCatalog | None = None) -> list[SchemaChunk]:
    chunks: list[SchemaChunk] = []
    aliases = aliases or AliasCatalog()
    for table in snapshot.tables:
        public_columns = [column for column in table.columns if not column.is_sensitive]
        sensitive_columns = [column.name for column in table.columns if column.is_sensitive]
        alias_lines = _alias_lines(table.name, aliases)
        lines = [
            "Database schema document for Qwen query planning.",
            f"Source: {snapshot.source_name}",
            f"Database: {snapshot.database_name}",
            f"Schema hash: {snapshot.schema_hash}",
            f"Table: {table.name}",
            f"Classification: {table.classification}",
            f"Approximate rows: {table.approximate_row_count}",
            f"Description: {table.business_description or table.comment or table.name}",
        ]
        if alias_lines:
            lines.append("Aliases: " + alias_lines)
        lines.append("Columns:")
        for column in public_columns:
            lines.append(
                "- "
                + json.dumps(
                    {
                        "name": column.name,
                        "type": column.data_type,
                        "nullable": column.nullable,
                        "primary_key": column.is_primary_key,
                        "foreign_key": column.is_foreign_key,
                        "indexed": column.is_indexed,
                        "comment": column.comment,
                        "enum_values": column.enum_like_values,
                        "safe_samples": column.safe_sample_values,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        if sensitive_columns:
            lines.append("Sensitive columns excluded from query plans: " + ", ".join(sorted(sensitive_columns)))
        lines.append("Primary key: " + json.dumps(table.primary_key_columns, ensure_ascii=False))
        lines.append("Foreign keys: " + json.dumps([fk.model_dump() for fk in table.foreign_keys], ensure_ascii=False, sort_keys=True))
        lines.append("Indexes: " + json.dumps([idx.model_dump() for idx in table.indexes], ensure_ascii=False, sort_keys=True))
        lines.append("Planning rules: never select sensitive columns, never output SQL, use only structured JSON plans.")
        content = "\n".join(lines)
        metadata = {
            "source_name": snapshot.source_name,
            "database_name": snapshot.database_name,
            "schema_hash": snapshot.schema_hash,
            "table_name": table.name,
            "classification": table.classification,
            "column_names": [column.name for column in public_columns],
            "sensitive_columns": sorted(sensitive_columns),
            "alias_hash": aliases.alias_hash,
        }
        chunks.append(
            SchemaChunk(
                chunk_id=stable_json_hash({"source": snapshot.source_name, "schema_hash": snapshot.schema_hash, "table": table.name})[:32],
                source_name=snapshot.source_name,
                schema_hash=snapshot.schema_hash,
                table_name=table.name,
                column_names=[column.name for column in public_columns],
                content=content,
                metadata=metadata,
                indexed_at=datetime.now(UTC),
            )
        )
    return chunks


def _alias_lines(table_name: str, aliases: AliasCatalog) -> str:
    parts = []
    for logical, entry in aliases.aliases.items():
        if table_name in entry.physical_candidates:
            names = entry.arabic + entry.english
            parts.append(f"{logical}: {', '.join(names)}")
    return "; ".join(parts)
