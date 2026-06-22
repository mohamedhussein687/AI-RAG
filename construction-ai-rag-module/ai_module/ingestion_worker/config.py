from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class TableConfig:
    name: str
    primary_key: str
    updated_at_column: str
    deleted_at_column: str | None
    document_template: str


@dataclass(frozen=True)
class SourceConfig:
    name: str
    tenant_id: str
    project_id: str
    tables: list[TableConfig]


def load_sources(path: str | Path) -> list[SourceConfig]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"RAG source config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    sources: list[SourceConfig] = []
    for source in raw.get("sources", []):
        tables = [
            TableConfig(
                name=str(table["name"]),
                primary_key=str(table.get("primary_key", "id")),
                updated_at_column=str(table.get("updated_at_column", "updated_at")),
                deleted_at_column=str(table["deleted_at_column"]) if table.get("deleted_at_column") else None,
                document_template=str(table.get("document_template", table["name"])),
            )
            for table in source.get("tables", [])
        ]
        sources.append(SourceConfig(name=str(source["name"]), tenant_id=str(source["tenant_id"]), project_id=str(source["project_id"]), tables=tables))
    return sources


def source_by_name(sources: list[SourceConfig], name: str | None) -> list[SourceConfig]:
    if not name:
        return sources
    selected = [source for source in sources if source.name == name]
    if not selected:
        raise ValueError(f"unknown RAG source: {name}")
    return selected


def table_by_name(source: SourceConfig, table_name: str | None) -> list[TableConfig]:
    if not table_name:
        return source.tables
    selected = [table for table in source.tables if table.name == table_name]
    if not selected:
        raise ValueError(f"unknown table for source {source.name}: {table_name}")
    return selected
