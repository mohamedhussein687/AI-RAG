from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.schema.schema_hash import calculate_schema_hash
from app.schema.schema_models import (
    AliasCatalog,
    SchemaColumn,
    SchemaForeignKey,
    SchemaIndex,
    SchemaSnapshot,
    SchemaTable,
    is_sensitive_field,
)


CMS_TABLE_TERMS = ("about", "page", "pages", "setting", "settings", "banner", "slider", "menu", "content", "cms", "blog")
SYSTEM_TABLE_TERMS = ("migration", "session", "cache", "job", "password_reset", "personal_access", "oauth", "log", "failed_jobs")
BUSINESS_TABLE_TERMS = ("project", "client", "customer", "contract", "task", "invoice", "payment", "user", "employee", "milestone", "progress")


async def discover_schema_from_connection(
    connection: Any,
    *,
    source_name: str,
    database_name: str,
    aliases: AliasCatalog | None = None,
    sample_limit: int = 8,
) -> SchemaSnapshot:
    tables = await _discover_tables(connection, database_name)
    columns_by_table = await _discover_columns(connection, database_name)
    indexes_by_table = await _discover_indexes(connection, database_name)
    fks_by_table = await _discover_foreign_keys(connection, database_name)

    schema_tables: list[SchemaTable] = []
    for row in tables:
        table_name = str(row["table_name"])
        index_items = indexes_by_table.get(table_name, [])
        fk_items = fks_by_table.get(table_name, [])
        pk_columns = [column.name for column in columns_by_table.get(table_name, []) if column.is_primary_key]
        indexed_columns = {column for index in index_items for column in index.columns}
        fk_columns = {fk.column for fk in fk_items}
        columns = []
        for column in columns_by_table.get(table_name, []):
            columns.append(
                column.model_copy(
                    update={
                        "is_indexed": column.name in indexed_columns or column.is_indexed,
                        "is_foreign_key": column.name in fk_columns or column.is_foreign_key,
                    }
                )
            )
        table = SchemaTable(
            name=table_name,
            comment=row.get("table_comment") or None,
            classification=classify_table(table_name),
            approximate_row_count=_int_or_none(row.get("table_rows")),
            primary_key_columns=pk_columns,
            indexes=index_items,
            foreign_keys=fk_items,
            business_description=_business_description(table_name, row.get("table_comment"), aliases),
            columns=columns,
        )
        table.safe_sample_summary = await _safe_samples(connection, table, limit=sample_limit)
        schema_tables.append(table)

    snapshot = SchemaSnapshot(
        source_name=source_name,
        database_name=database_name,
        schema_hash="pending",
        alias_hash=aliases.alias_hash if aliases else None,
        tables=schema_tables,
    )
    return snapshot.model_copy(update={"schema_hash": calculate_schema_hash(snapshot, aliases)})


async def _discover_tables(connection: Any, database_name: str) -> list[dict[str, Any]]:
    sql = """
        select table_name, table_comment, table_rows
        from information_schema.tables
        where table_schema = %s and table_type = 'BASE TABLE'
        order by table_name
    """
    return await _fetchall(connection, sql, [database_name])


async def _discover_columns(connection: Any, database_name: str) -> dict[str, list[SchemaColumn]]:
    sql = """
        select table_name, column_name, data_type, column_type, is_nullable, column_default, column_comment, column_key
        from information_schema.columns
        where table_schema = %s
        order by table_name, ordinal_position
    """
    rows = await _fetchall(connection, sql, [database_name])
    columns: dict[str, list[SchemaColumn]] = defaultdict(list)
    for row in rows:
        name = str(row["column_name"])
        column = SchemaColumn(
            name=name,
            data_type=str(row.get("data_type") or row.get("column_type") or ""),
            nullable=str(row.get("is_nullable", "YES")).upper() == "YES",
            default_value=None if row.get("column_default") is None else str(row.get("column_default")),
            comment=row.get("column_comment") or None,
            is_primary_key=str(row.get("column_key", "")).upper() == "PRI",
            is_indexed=str(row.get("column_key", "")).upper() in {"PRI", "MUL", "UNI"},
            is_sensitive=is_sensitive_field(name),
            enum_like_values=_enum_values(str(row.get("column_type") or "")),
        )
        columns[str(row["table_name"])].append(column)
    return columns


async def _discover_indexes(connection: Any, database_name: str) -> dict[str, list[SchemaIndex]]:
    sql = """
        select table_name, index_name, column_name, non_unique, seq_in_index
        from information_schema.statistics
        where table_schema = %s
        order by table_name, index_name, seq_in_index
    """
    rows = await _fetchall(connection, sql, [database_name])
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["table_name"]), str(row["index_name"]))
        grouped.setdefault(key, {"columns": [], "unique": not bool(row.get("non_unique"))})
        grouped[key]["columns"].append(str(row["column_name"]))
    by_table: dict[str, list[SchemaIndex]] = defaultdict(list)
    for (table_name, index_name), value in grouped.items():
        by_table[table_name].append(SchemaIndex(name=index_name, columns=value["columns"], unique=value["unique"]))
    return by_table


async def _discover_foreign_keys(connection: Any, database_name: str) -> dict[str, list[SchemaForeignKey]]:
    sql = """
        select table_name, column_name, referenced_table_name, referenced_column_name, constraint_name
        from information_schema.key_column_usage
        where table_schema = %s and referenced_table_name is not null
        order by table_name, column_name
    """
    rows = await _fetchall(connection, sql, [database_name])
    by_table: dict[str, list[SchemaForeignKey]] = defaultdict(list)
    for row in rows:
        by_table[str(row["table_name"])].append(
            SchemaForeignKey(
                column=str(row["column_name"]),
                referenced_table=str(row["referenced_table_name"]),
                referenced_column=str(row["referenced_column_name"]),
                constraint_name=str(row["constraint_name"]) if row.get("constraint_name") else None,
            )
        )
    return by_table


async def _safe_samples(connection: Any, table: SchemaTable, *, limit: int) -> dict[str, list[Any]]:
    samples: dict[str, list[Any]] = {}
    for column in table.columns:
        if column.is_sensitive or not _can_sample(column):
            continue
        sql = f"select `{column.name}` from `{table.name}` where `{column.name}` is not null group by `{column.name}` limit %s"
        try:
            rows = await _fetchall(connection, sql, [limit])
        except Exception:
            continue
        values = [row.get(column.name) for row in rows if row.get(column.name) not in (None, "")]
        safe = [str(value)[:120] for value in values[:limit]]
        if safe:
            samples[column.name] = safe
            column.safe_sample_values = safe
            if not column.enum_like_values and len(safe) <= limit:
                column.enum_like_values = safe
    return samples


async def _fetchall(connection: Any, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    async with connection.cursor() as cursor:
        await cursor.execute(sql, params or [])
        return list(await cursor.fetchall())


def classify_table(table_name: str) -> str:
    normalized = table_name.lower()
    if any(term in normalized for term in SYSTEM_TABLE_TERMS):
        return "system"
    if any(term in normalized for term in CMS_TABLE_TERMS):
        return "cms_content"
    if any(term in normalized for term in BUSINESS_TABLE_TERMS):
        return "business"
    return "unknown"


def _business_description(table_name: str, comment: str | None, aliases: AliasCatalog | None) -> str | None:
    alias_hits = []
    if aliases:
        for logical, entry in aliases.aliases.items():
            if table_name in entry.physical_candidates:
                alias_hits.append(logical)
    parts = [part for part in [comment, f"logical aliases: {', '.join(alias_hits)}" if alias_hits else None] if part]
    return "; ".join(parts) if parts else None


def _enum_values(column_type: str) -> list[str]:
    match = re.match(r"enum\((.*)\)", column_type, flags=re.IGNORECASE)
    if not match:
        return []
    return [item.replace("\\'", "'") for item in re.findall(r"'((?:\\'|[^'])*)'", match.group(1))]


def _can_sample(column: SchemaColumn) -> bool:
    return column.data_type.lower() in {"varchar", "char", "enum", "set", "tinyint", "smallint", "int", "bigint", "bool", "boolean"}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
