from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiomysql

from app.schema.schema_models import is_sensitive_field, stable_json_hash


IDENTIFIER_RE = re.compile(r"[^a-z0-9]+")


async def run_schema_catalog(args: argparse.Namespace) -> int:
    args.password = args.password or os.getenv(args.password_env or "MYSQL_PASSWORD", "")
    if not args.password:
        raise SystemExit("schema-catalog requires --password or --password-env pointing to a set environment variable")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    final_path = output_dir / "catalog.json"

    async with _connect(args) as connection:
        tables = await _fetch_tables(connection, args.database)
        table_names = [row["table_name"] for row in tables]
        manifest = _read_manifest(manifest_path)
        completed = set(manifest.get("completed_tables") or [])

        for ordinal, table_row in enumerate(tables, start=1):
            table_name = str(table_row["table_name"])
            table_path = tables_dir / f"{_safe_filename(table_name)}.json"
            if not args.force and table_name in completed and table_path.exists():
                print(f"schema_catalog table={table_name} status=skipped progress={ordinal}/{len(tables)}")
                continue

            catalog_table = await _build_table_catalog(connection, args.database, table_row)
            _write_json_atomic(table_path, catalog_table)
            completed.add(table_name)
            manifest = {
                "database": args.database,
                "generated_at": datetime.now(UTC).isoformat(),
                "table_count": len(tables),
                "completed_count": len(completed),
                "completed_tables": sorted(completed),
                "pending_tables": [name for name in table_names if name not in completed],
                "final_catalog": str(final_path),
            }
            _write_json_atomic(manifest_path, manifest)
            print(f"schema_catalog table={table_name} status=written progress={ordinal}/{len(tables)}")

        table_catalogs = []
        missing = []
        for table_name in table_names:
            table_path = tables_dir / f"{_safe_filename(table_name)}.json"
            if not table_path.exists():
                missing.append(table_name)
                continue
            table_catalogs.append(json.loads(table_path.read_text(encoding="utf-8")))

        if missing:
            _write_json_atomic(
                manifest_path,
                {
                    **manifest,
                    "completed_count": len(table_catalogs),
                    "pending_tables": missing,
                    "status": "incomplete",
                },
            )
            print(f"schema_catalog status=incomplete missing={len(missing)} output={output_dir}")
            return 2

        relationships = _global_relationships(table_catalogs)
        catalog = {
            "database": args.database,
            "generated_at": datetime.now(UTC).isoformat(),
            "source": {
                "host": args.host,
                "port": args.port,
                "schema": args.database,
            },
            "table_count": len(table_catalogs),
            "column_count": sum(len(table["columns"]) for table in table_catalogs),
            "relationship_count": len(relationships),
            "schema_hash": stable_json_hash(table_catalogs),
            "tables": table_catalogs,
            "relationships": relationships,
        }
        _write_json_atomic(final_path, catalog)
        _write_json_atomic(
            manifest_path,
            {
                **manifest,
                "generated_at": catalog["generated_at"],
                "completed_count": len(table_catalogs),
                "pending_tables": [],
                "status": "complete",
                "schema_hash": catalog["schema_hash"],
            },
        )
        print(
            "schema_catalog status=complete "
            f"tables={catalog['table_count']} columns={catalog['column_count']} "
            f"relationships={catalog['relationship_count']} output={final_path}"
        )
        return 0


class _ConnectionContext:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.connection: aiomysql.Connection | None = None

    async def __aenter__(self) -> aiomysql.Connection:
        self.connection = await aiomysql.connect(
            host=self.args.host,
            port=self.args.port,
            user=self.args.user,
            password=self.args.password,
            db=self.args.database,
            autocommit=True,
            connect_timeout=self.args.connect_timeout,
            cursorclass=aiomysql.DictCursor,
        )
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.connection is not None:
            self.connection.close()
            await self.connection.ensure_closed()


def _connect(args: argparse.Namespace) -> _ConnectionContext:
    return _ConnectionContext(args)


async def _build_table_catalog(connection: aiomysql.Connection, database: str, table_row: dict[str, Any]) -> dict[str, Any]:
    table_name = str(table_row["table_name"])
    columns = await _fetch_columns(connection, database, table_name)
    indexes = await _fetch_indexes(connection, database, table_name)
    foreign_keys = await _fetch_foreign_keys(connection, database, table_name)
    inbound_foreign_keys = await _fetch_inbound_foreign_keys(connection, database, table_name)

    primary_keys = [column["name"] for column in columns if column["primary_key"]]
    unique_keys = [index for index in indexes if index["unique"] and index["name"] != "PRIMARY"]
    relationships = _table_relationships(table_name, foreign_keys, inbound_foreign_keys)
    keywords = _keywords(table_name, table_row, columns, foreign_keys, inbound_foreign_keys)
    semantic = _semantic_description(table_name, table_row, columns, relationships, keywords)

    return {
        "table": table_name,
        "table_comment": table_row.get("table_comment") or None,
        "engine": table_row.get("engine"),
        "row_count_estimate": _int_or_none(table_row.get("table_rows")),
        "primary_keys": primary_keys,
        "unique_keys": unique_keys,
        "indexes": indexes,
        "foreign_keys": foreign_keys,
        "relationships": relationships,
        "columns": columns,
        "description": semantic["description"],
        "business_purpose": semantic["business_purpose"],
        "probable_meaning": semantic["probable_meaning"],
        "relationship_summary": semantic["relationship_summary"],
        "important_columns": semantic["important_columns"],
        "common_query_patterns": semantic["common_query_patterns"],
        "keywords": keywords,
    }


async def _fetch_tables(connection: aiomysql.Connection, database: str) -> list[dict[str, Any]]:
    return await _fetchall(
        connection,
        """
        select table_name, table_comment, table_rows, engine, create_time, update_time, table_collation
        from information_schema.tables
        where table_schema = %s and table_type = 'BASE TABLE'
        order by table_name
        """,
        [database],
    )


async def _fetch_columns(connection: aiomysql.Connection, database: str, table_name: str) -> list[dict[str, Any]]:
    rows = await _fetchall(
        connection,
        """
        select
            table_name, column_name, ordinal_position, column_default, is_nullable,
            data_type, column_type, character_maximum_length, numeric_precision,
            numeric_scale, datetime_precision, character_set_name, collation_name,
            column_key, extra, column_comment, generation_expression
        from information_schema.columns
        where table_schema = %s and table_name = %s
        order by ordinal_position
        """,
        [database, table_name],
    )
    columns = []
    for row in rows:
        name = str(row["column_name"])
        extra = str(row.get("extra") or "")
        columns.append(
            {
                "name": name,
                "ordinal_position": _int_or_none(row.get("ordinal_position")),
                "data_type": row.get("data_type"),
                "column_type": row.get("column_type"),
                "nullable": str(row.get("is_nullable") or "").upper() == "YES",
                "default_value": None if row.get("column_default") is None else str(row.get("column_default")),
                "auto_increment": "auto_increment" in extra.lower(),
                "extra": extra,
                "primary_key": str(row.get("column_key") or "").upper() == "PRI",
                "unique_key": str(row.get("column_key") or "").upper() == "UNI",
                "indexed": str(row.get("column_key") or "").upper() in {"PRI", "UNI", "MUL"},
                "sensitive": is_sensitive_field(name),
                "comment": row.get("column_comment") or None,
                "character_maximum_length": _int_or_none(row.get("character_maximum_length")),
                "numeric_precision": _int_or_none(row.get("numeric_precision")),
                "numeric_scale": _int_or_none(row.get("numeric_scale")),
                "datetime_precision": _int_or_none(row.get("datetime_precision")),
                "character_set_name": row.get("character_set_name"),
                "collation_name": row.get("collation_name"),
                "generation_expression": row.get("generation_expression") or None,
                "semantic_description": _column_description(name, row),
            }
        )
    return columns


async def _fetch_indexes(connection: aiomysql.Connection, database: str, table_name: str) -> list[dict[str, Any]]:
    rows = await _fetchall(
        connection,
        """
        select
            index_name, non_unique, seq_in_index, column_name, sub_part,
            index_type, nullable, collation, cardinality
        from information_schema.statistics
        where table_schema = %s and table_name = %s
        order by index_name, seq_in_index
        """,
        [database, table_name],
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row["index_name"])
        grouped.setdefault(
            name,
            {
                "name": name,
                "unique": not bool(row.get("non_unique")),
                "type": row.get("index_type"),
                "columns": [],
            },
        )
        grouped[name]["columns"].append(
            {
                "name": row.get("column_name"),
                "sequence": _int_or_none(row.get("seq_in_index")),
                "prefix_length": _int_or_none(row.get("sub_part")),
                "nullable": row.get("nullable"),
                "collation": row.get("collation"),
                "cardinality": _int_or_none(row.get("cardinality")),
            }
        )
    return list(grouped.values())


async def _fetch_foreign_keys(connection: aiomysql.Connection, database: str, table_name: str) -> list[dict[str, Any]]:
    return await _fetchall(
        connection,
        """
        select
            kcu.constraint_name, kcu.column_name, kcu.ordinal_position,
            kcu.referenced_table_name, kcu.referenced_column_name,
            rc.update_rule, rc.delete_rule
        from information_schema.key_column_usage kcu
        left join information_schema.referential_constraints rc
          on rc.constraint_schema = kcu.constraint_schema
         and rc.constraint_name = kcu.constraint_name
         and rc.table_name = kcu.table_name
        where kcu.table_schema = %s
          and kcu.table_name = %s
          and kcu.referenced_table_name is not null
        order by kcu.constraint_name, kcu.ordinal_position
        """,
        [database, table_name],
    )


async def _fetch_inbound_foreign_keys(connection: aiomysql.Connection, database: str, table_name: str) -> list[dict[str, Any]]:
    return await _fetchall(
        connection,
        """
        select
            kcu.table_name, kcu.constraint_name, kcu.column_name,
            kcu.referenced_column_name, rc.update_rule, rc.delete_rule
        from information_schema.key_column_usage kcu
        left join information_schema.referential_constraints rc
          on rc.constraint_schema = kcu.constraint_schema
         and rc.constraint_name = kcu.constraint_name
         and rc.table_name = kcu.table_name
        where kcu.table_schema = %s
          and kcu.referenced_table_name = %s
        order by kcu.table_name, kcu.constraint_name, kcu.ordinal_position
        """,
        [database, table_name],
    )


async def _fetchall(connection: aiomysql.Connection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    async with connection.cursor() as cursor:
        await cursor.execute(sql, params)
        return list(await cursor.fetchall())


def _table_relationships(
    table_name: str,
    foreign_keys: list[dict[str, Any]],
    inbound_foreign_keys: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    relationships = []
    for fk in foreign_keys:
        relationships.append(
            {
                "direction": "outbound",
                "type": "many_to_one",
                "from_table": table_name,
                "from_column": fk["column_name"],
                "to_table": fk["referenced_table_name"],
                "to_column": fk["referenced_column_name"],
                "constraint_name": fk.get("constraint_name"),
                "update_rule": fk.get("update_rule"),
                "delete_rule": fk.get("delete_rule"),
            }
        )
    for fk in inbound_foreign_keys:
        relationships.append(
            {
                "direction": "inbound",
                "type": "one_to_many",
                "from_table": fk["table_name"],
                "from_column": fk["column_name"],
                "to_table": table_name,
                "to_column": fk["referenced_column_name"],
                "constraint_name": fk.get("constraint_name"),
                "update_rule": fk.get("update_rule"),
                "delete_rule": fk.get("delete_rule"),
            }
        )
    return relationships


def _global_relationships(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relationships = []
    seen = set()
    for table in tables:
        for relationship in table["relationships"]:
            if relationship["direction"] != "outbound":
                continue
            key = (
                relationship["constraint_name"],
                relationship["from_table"],
                relationship["from_column"],
                relationship["to_table"],
                relationship["to_column"],
            )
            if key in seen:
                continue
            seen.add(key)
            relationships.append(relationship)
    return relationships


def _semantic_description(
    table_name: str,
    table_row: dict[str, Any],
    columns: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    keywords: list[str],
) -> dict[str, Any]:
    comment = table_row.get("table_comment") or ""
    important = _important_columns(columns)
    outbound = [item for item in relationships if item["direction"] == "outbound"]
    inbound = [item for item in relationships if item["direction"] == "inbound"]
    readable_name = table_name.replace("_", " ")

    purpose = comment.strip() or f"Stores {readable_name} records used by the application."
    meaning_bits = []
    if important:
        meaning_bits.append("Key fields include " + ", ".join(important[:8]) + ".")
    if outbound:
        meaning_bits.append(
            "References "
            + ", ".join(sorted({str(item["to_table"]) for item in outbound})[:8])
            + "."
        )
    if inbound:
        meaning_bits.append(
            "Referenced by "
            + ", ".join(sorted({str(item["from_table"]) for item in inbound})[:8])
            + "."
        )
    probable_meaning = " ".join(meaning_bits) or f"Represents operational data for {readable_name}."
    relationship_summary = _relationship_summary(outbound, inbound)
    query_patterns = _query_patterns(table_name, columns, outbound, inbound)

    return {
        "description": f"{purpose} {probable_meaning}".strip(),
        "business_purpose": purpose,
        "probable_meaning": probable_meaning,
        "relationship_summary": relationship_summary,
        "important_columns": important,
        "common_query_patterns": query_patterns,
        "keywords": keywords,
    }


def _column_description(name: str, row: dict[str, Any]) -> str:
    comment = row.get("column_comment")
    if comment:
        return str(comment)
    normalized = name.lower()
    if normalized == "id" or normalized.endswith("_id"):
        return "Identifier or relationship key."
    if "created" in normalized:
        return "Creation timestamp or creator reference."
    if "updated" in normalized:
        return "Last update timestamp or updater reference."
    if "status" in normalized or "state" in normalized:
        return "Lifecycle state used for filtering and workflow decisions."
    if "name" in normalized or "title" in normalized:
        return "Human-readable label used for lookup and display."
    if "amount" in normalized or "price" in normalized or "cost" in normalized or "total" in normalized:
        return "Numeric business value commonly used in summaries and totals."
    return f"{row.get('column_type') or row.get('data_type')} value for {name.replace('_', ' ')}."


def _important_columns(columns: list[dict[str, Any]]) -> list[str]:
    scored = []
    for index, column in enumerate(columns):
        name = column["name"]
        score = 0
        if column["primary_key"]:
            score += 100
        if column["unique_key"]:
            score += 50
        if column["indexed"]:
            score += 25
        if name.endswith("_id"):
            score += 20
        if any(term in name.lower() for term in ("name", "title", "status", "type", "date", "amount", "total", "created_at", "updated_at")):
            score += 15
        scored.append((-score, index, name))
    return [name for _, _, name in sorted(scored)[:12]]


def _relationship_summary(outbound: list[dict[str, Any]], inbound: list[dict[str, Any]]) -> str:
    parts = []
    if outbound:
        parts.append("joins outward to " + ", ".join(sorted({str(item["to_table"]) for item in outbound})[:10]))
    if inbound:
        parts.append("receives references from " + ", ".join(sorted({str(item["from_table"]) for item in inbound})[:10]))
    return "; ".join(parts) if parts else "No explicit foreign-key relationships were found in information_schema."


def _query_patterns(
    table_name: str,
    columns: list[dict[str, Any]],
    outbound: list[dict[str, Any]],
    inbound: list[dict[str, Any]],
) -> list[str]:
    names = [column["name"] for column in columns]
    patterns = [f"List or count {table_name} records."]
    for candidate in ("status", "type", "created_at", "updated_at", "date"):
        matches = [name for name in names if candidate in name.lower()]
        if matches:
            patterns.append(f"Filter {table_name} by {matches[0]}.")
    for fk in outbound[:5]:
        patterns.append(f"Join {table_name}.{fk['from_column']} to {fk['to_table']}.{fk['to_column']}.")
    for fk in inbound[:5]:
        patterns.append(f"Find {fk['from_table']} rows related to a {table_name} record.")
    return patterns


def _keywords(
    table_name: str,
    table_row: dict[str, Any],
    columns: list[dict[str, Any]],
    foreign_keys: list[dict[str, Any]],
    inbound_foreign_keys: list[dict[str, Any]],
) -> list[str]:
    values = [table_name, table_name.replace("_", " "), table_row.get("table_comment") or ""]
    values.extend(column["name"] for column in columns)
    values.extend(str(fk["referenced_table_name"]) for fk in foreign_keys)
    values.extend(str(fk["table_name"]) for fk in inbound_foreign_keys)
    words = []
    for value in values:
        words.extend(part for part in IDENTIFIER_RE.split(str(value).lower()) if len(part) > 1)
    seen = set()
    result = []
    for word in words:
        if word not in seen:
            seen.add(word)
            result.append(word)
    return result


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _safe_filename(table_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", table_name)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def add_schema_catalog_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subcommands.add_parser("schema-catalog", help="build a complete resumable information_schema catalog")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--database", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default="")
    parser.add_argument("--password-env", default="MYSQL_PASSWORD")
    parser.add_argument("--output-dir", default="outputs/schema_catalog")
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--query-timeout", type=int, default=60)
    parser.add_argument("--force", action="store_true")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ingestion_worker.schema_catalog_builder")
    subcommands = parser.add_subparsers(dest="command")
    add_schema_catalog_parser(subcommands)
    args = parser.parse_args()
    if args.command != "schema-catalog":
        parser.error("missing command")
    raise SystemExit(asyncio.run(run_schema_catalog(args)))


if __name__ == "__main__":
    main()
