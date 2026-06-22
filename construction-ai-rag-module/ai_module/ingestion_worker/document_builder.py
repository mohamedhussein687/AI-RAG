from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ingestion_worker.config import SourceConfig, TableConfig


@dataclass(frozen=True)
class BuiltDocument:
    title: str
    content: str
    metadata: dict[str, Any]
    document_hash: str
    content_preview: str


SENSITIVE_FIELD_PATTERNS = re.compile(r"(password|token|secret|private_key|remember_token|api_key|reset_token)", re.IGNORECASE)


def build_document(source: SourceConfig, table: TableConfig, row: dict[str, Any]) -> BuiltDocument:
    source_id = str(row[table.primary_key])
    title = _title_for(table, row, source_id)
    content = _render_template(table.document_template, row)
    normalized = normalize_content(content)
    document_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    metadata = {
        "tenant_id": source.tenant_id,
        "project_id": source.project_id,
        "source_name": source.name,
        "source_table": table.name,
        "source_id": source_id,
        "source_updated_at": _stringify(row.get(table.updated_at_column)),
        "document_template": table.document_template,
        "source_identity": f"{source.name}:{table.name}:{source_id}",
    }
    for key in ("status", "project_status", "condition", "type"):
        if key in row and row[key] is not None:
            metadata["source_status"] = str(row[key])
            break
    return BuiltDocument(title=title, content=content, metadata=metadata, document_hash=document_hash, content_preview=normalized[:500])


def normalize_content(content: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in content.splitlines()]
    return "\n".join(line for line in lines if line)


def _render_template(template: str, row: dict[str, Any]) -> str:
    if template == "construction_project":
        return _render_project(row)
    if template == "construction_task":
        return _render_task(row)
    if template == "client":
        return _render_client(row)
    return _render_generic(row)


def _render_project(row: dict[str, Any]) -> str:
    fields = [
        ("Project Name / اسم المشروع", _first(row, "name", "title", "project_name", "project_title")),
        ("Project Code / كود المشروع", _first(row, "code", "project_code", "project_serial", "reference", "ref_no", "number")),
        ("Status / الحالة", _first(row, "status", "project_status", "condition", "state")),
        ("Client / العميل", _first(row, "client_name", "client", "customer_name")),
        ("Location / الموقع", _first(row, "location", "address", "city")),
        ("Description / الوصف", _first(row, "description", "introduction", "notes")),
        ("Start Date / تاريخ البداية", _first(row, "start_date", "started_at")),
        ("End Date / تاريخ النهاية", _first(row, "end_date", "finish_date", "plan_finish", "deadline", "delivery_date", "planned_delivery_date")),
        ("Progress / نسبة الإنجاز", _first(row, "progress", "completion_percentage", "percent_complete")),
        ("Updated At / آخر تحديث", _first(row, "updated_at", "modified_at")),
    ]
    return _format_fields(fields)


def _render_task(row: dict[str, Any]) -> str:
    fields = [
        ("Task / المهمة", _first(row, "name", "title", "task_name")),
        ("Status / الحالة", _first(row, "status", "task_status", "state")),
        ("Project ID / رقم المشروع", _first(row, "project_id")),
        ("Description / الوصف", _first(row, "description", "notes")),
        ("Due Date / تاريخ الاستحقاق", _first(row, "due_date", "deadline", "end_date")),
        ("Updated At / آخر تحديث", _first(row, "updated_at")),
    ]
    return _format_fields(fields)


def _render_client(row: dict[str, Any]) -> str:
    fields = [
        ("Client / العميل", _first(row, "name", "title", "client_name", "customer_name")),
        ("Status / الحالة", _first(row, "status", "client_status")),
        ("Phone / الهاتف", _first(row, "phone", "mobile")),
        ("Email / البريد", _first(row, "email")),
        ("Address / العنوان", _first(row, "address", "city")),
        ("Updated At / آخر تحديث", _first(row, "updated_at")),
    ]
    return _format_fields(fields)


def _render_generic(row: dict[str, Any]) -> str:
    fields = [(key.replace("_", " ").title(), value) for key, value in row.items() if not SENSITIVE_FIELD_PATTERNS.search(key)]
    return _format_fields(fields)


def _format_fields(fields: list[tuple[str, Any]]) -> str:
    return "\n".join(f"{label}: {_stringify(value)}" for label, value in fields if value not in (None, ""))


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _title_for(table: TableConfig, row: dict[str, Any], source_id: str) -> str:
    value = _first(row, "name", "title", "project_name", "client_name", "task_name", "code", "project_code", "project_serial")
    return str(value) if value else f"{table.name} #{source_id}"


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
