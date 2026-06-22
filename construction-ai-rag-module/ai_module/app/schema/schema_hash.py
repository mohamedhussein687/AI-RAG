from __future__ import annotations

from typing import Any

from app.schema.schema_models import AliasCatalog, SchemaSnapshot, stable_json_hash


def canonical_schema(snapshot: SchemaSnapshot) -> dict[str, Any]:
    return {
        "source_name": snapshot.source_name,
        "database_name": snapshot.database_name,
        "tables": [
            {
                "name": table.name,
                "comment": table.comment,
                "classification": table.classification,
                "approximate_row_count": table.approximate_row_count,
                "primary_key_columns": sorted(table.primary_key_columns),
                "indexes": sorted(
                    [{"name": index.name, "columns": index.columns, "unique": index.unique} for index in table.indexes],
                    key=lambda item: (item["name"], item["columns"]),
                ),
                "foreign_keys": sorted(
                    [
                        {
                            "column": fk.column,
                            "referenced_table": fk.referenced_table,
                            "referenced_column": fk.referenced_column,
                            "constraint_name": fk.constraint_name,
                        }
                        for fk in table.foreign_keys
                    ],
                    key=lambda item: (item["column"], item["referenced_table"], item["referenced_column"]),
                ),
                "columns": [
                    {
                        "name": column.name,
                        "data_type": column.data_type,
                        "nullable": column.nullable,
                        "default_value": column.default_value,
                        "comment": column.comment,
                        "is_primary_key": column.is_primary_key,
                        "is_foreign_key": column.is_foreign_key,
                        "is_indexed": column.is_indexed,
                        "is_sensitive": column.is_sensitive,
                        "enum_like_values": column.enum_like_values,
                    }
                    for column in sorted(table.columns, key=lambda item: item.name)
                ],
            }
            for table in sorted(snapshot.tables, key=lambda item: item.name)
        ],
    }


def calculate_schema_hash(snapshot: SchemaSnapshot, aliases: AliasCatalog | None = None) -> str:
    payload: dict[str, Any] = {"schema": canonical_schema(snapshot)}
    if aliases is not None:
        payload["alias_hash"] = aliases.alias_hash
    return stable_json_hash(payload)
