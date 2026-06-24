from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SENSITIVE_FIELD_TERMS = frozenset(
    {
        "password",
        "passwd",
        "pass",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
        "otp",
        "verification_code",
        "reset_token",
        "remember_token",
        "auth",
        "credential",
    }
)

RAW_SQL_PATTERN = re.compile(r"\b(select|insert|update|delete|drop|alter|truncate|create|grant|revoke|call|exec|union)\b", re.IGNORECASE)
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_sensitive_field(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9_]+", "_", name.lower())
    parts = {part for part in normalized.split("_") if part}
    return normalized in SENSITIVE_FIELD_TERMS or bool(parts & SENSITIVE_FIELD_TERMS)


def redact_sensitive_mapping(values: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in values.items():
        redacted[key] = "[REDACTED]" if is_sensitive_field(key) else value
    return redacted


def stable_json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SchemaColumn(StrictModel):
    name: str
    data_type: str
    nullable: bool = True
    default_value: str | None = None
    comment: str | None = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_indexed: bool = False
    is_sensitive: bool = False
    enum_like_values: list[str] = Field(default_factory=list)
    safe_sample_values: list[Any] = Field(default_factory=list)
    semantic_description: str | None = None

    @model_validator(mode="after")
    def infer_sensitive(self) -> "SchemaColumn":
        if is_sensitive_field(self.name):
            self.is_sensitive = True
            self.safe_sample_values = []
        return self


class SchemaForeignKey(StrictModel):
    column: str
    referenced_table: str
    referenced_column: str
    constraint_name: str | None = None


class SchemaIndex(StrictModel):
    name: str
    columns: list[str]
    unique: bool = False


class SchemaTable(StrictModel):
    name: str
    comment: str | None = None
    classification: Literal["business", "cms_content", "system", "unknown"] = "unknown"
    approximate_row_count: int | None = None
    primary_key_columns: list[str] = Field(default_factory=list)
    indexes: list[SchemaIndex] = Field(default_factory=list)
    foreign_keys: list[SchemaForeignKey] = Field(default_factory=list)
    business_description: str | None = None
    safe_sample_summary: dict[str, Any] = Field(default_factory=dict)
    columns: list[SchemaColumn] = Field(default_factory=list)

    def column(self, name: str) -> SchemaColumn | None:
        return next((column for column in self.columns if column.name == name), None)

    def safe_columns(self) -> list[SchemaColumn]:
        return [column for column in self.columns if not column.is_sensitive]


class AliasEntry(StrictModel):
    arabic: list[str] = Field(default_factory=list)
    english: list[str] = Field(default_factory=list)
    physical_candidates: list[str] = Field(default_factory=list)
    notes: str | None = None


class AliasCatalog(StrictModel):
    version: str = "v1"
    file_path: str | None = None
    aliases: dict[str, AliasEntry] = Field(default_factory=dict)
    alias_hash: str | None = None

    @model_validator(mode="after")
    def calculate_hash(self) -> "AliasCatalog":
        if not self.alias_hash:
            self.alias_hash = stable_json_hash({"version": self.version, "aliases": self.model_dump(exclude={"alias_hash", "file_path"})["aliases"]})
        return self


def load_alias_catalog(path: str | Path | None) -> AliasCatalog:
    if not path:
        return AliasCatalog()
    alias_path = Path(path)
    if not alias_path.exists():
        return AliasCatalog(file_path=str(alias_path))
    with alias_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    entries: dict[str, AliasEntry] = {}
    for key, value in (raw.get("aliases") or {}).items():
        entries[str(key)] = AliasEntry(
            arabic=[str(item) for item in value.get("arabic", [])],
            english=[str(item) for item in value.get("english", [])],
            physical_candidates=[str(item) for item in value.get("physical_candidates", [])],
            notes=str(value["notes"]) if value.get("notes") else None,
        )
    return AliasCatalog(version=str(raw.get("version", "v1")), file_path=str(alias_path), aliases=entries)


class SchemaSnapshot(StrictModel):
    source_name: str
    database_name: str
    schema_hash: str
    alias_hash: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["fresh", "stale", "failed"] = "fresh"
    tables: list[SchemaTable] = Field(default_factory=list)
    error_message: str | None = None

    def table(self, name: str) -> SchemaTable | None:
        return next((table for table in self.tables if table.name == name), None)

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def column_count(self) -> int:
        return sum(len(table.columns) for table in self.tables)

    @property
    def relationship_count(self) -> int:
        return sum(len(table.foreign_keys) for table in self.tables)

    @property
    def sensitive_field_count(self) -> int:
        return sum(1 for table in self.tables for column in table.columns if column.is_sensitive)


class QueryFilter(StrictModel):
    column: str
    operator: Literal["=", "!=", ">", ">=", "<", "<=", "in", "like", "is_null", "is_not_null"]
    value: Any = None


class QueryOrderBy(StrictModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class QueryJoin(StrictModel):
    table: str
    left_column: str
    right_column: str
    type: Literal["inner", "left"] = "inner"


class StructuredQueryPlan(StrictModel):
    route: Literal["database_query", "hybrid"] = "database_query"
    operation: str
    logical_entities: list[str] = Field(default_factory=list)
    resolved_tables: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    joins: list[QueryJoin] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    order_by: list[QueryOrderBy] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1)
    requires_confirmation: bool = False
    raw_sql: str | None = None

    @field_validator("columns", "resolved_tables", "group_by")
    @classmethod
    def reject_raw_sql_in_identifiers(cls, values: list[str]) -> list[str]:
        for value in values:
            if RAW_SQL_PATTERN.search(value):
                raise ValueError("raw SQL is not allowed in structured plans")
        return values


class ValidatedQueryPlan(StrictModel):
    operation: Literal["select", "count", "aggregate"]
    table: str
    columns: list[str]
    filters: list[QueryFilter] = Field(default_factory=list)
    joins: list[QueryJoin] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    order_by: list[QueryOrderBy] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1)
    aggregate_function: Literal["sum", "avg", "min", "max"] | None = None
    aggregate_column: str | None = None


class QueryExecution(StrictModel):
    rows: list[dict[str, Any]]
    summary: dict[str, Any]
    elapsed_ms: float | None = None
