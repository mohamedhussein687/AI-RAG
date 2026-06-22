from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schema.schema_models import AliasCatalog, AliasEntry, SchemaColumn, SchemaSnapshot, SchemaTable
from training.dataset_builder import build_dataset, validate_dataset, write_jsonl


def _snapshot() -> SchemaSnapshot:
    return SchemaSnapshot(
        source_name="construction_mysql",
        database_name="construction_ai_dev",
        schema_hash="test-schema-hash",
        alias_hash="test-alias-hash",
        tables=[
            SchemaTable(
                name="users",
                classification="business",
                approximate_row_count=42,
                primary_key_columns=["id"],
                business_description="System users and account records",
                columns=[
                    SchemaColumn(name="id", data_type="int", is_primary_key=True, is_indexed=True),
                    SchemaColumn(name="name", data_type="varchar", safe_sample_values=["Ayman Ibrahim El Sayed", "Basma Al Kholy"]),
                    SchemaColumn(name="email", data_type="varchar", safe_sample_values=["masked@example.test"]),
                    SchemaColumn(name="type", data_type="int", enum_like_values=["1", "2"], safe_sample_values=["1", "2"]),
                    SchemaColumn(name="password", data_type="varchar", is_sensitive=True, safe_sample_values=["secret-password"]),
                    SchemaColumn(name="remember_token", data_type="varchar", is_sensitive=True, safe_sample_values=["token-value"]),
                    SchemaColumn(name="created_at", data_type="datetime"),
                ],
            ),
            SchemaTable(
                name="projects",
                classification="business",
                approximate_row_count=7,
                primary_key_columns=["id"],
                business_description="Construction projects",
                columns=[
                    SchemaColumn(name="id", data_type="int", is_primary_key=True),
                    SchemaColumn(name="name", data_type="varchar", safe_sample_values=["test60"]),
                    SchemaColumn(name="project_status", data_type="varchar", enum_like_values=["waiting", "active"], safe_sample_values=["waiting", "active"]),
                    SchemaColumn(name="created_at", data_type="datetime"),
                    SchemaColumn(name="updated_at", data_type="datetime"),
                ],
            ),
            SchemaTable(
                name="about_us",
                classification="cms_content",
                columns=[SchemaColumn(name="title", data_type="varchar")],
            ),
        ],
    )


def _aliases() -> AliasCatalog:
    return AliasCatalog(
        aliases={
            "users": AliasEntry(
                arabic=["المستخدمين", "المستخدم"],
                english=["users", "user"],
                physical_candidates=["users"],
            ),
            "projects": AliasEntry(
                arabic=["المشاريع", "المشروع"],
                english=["projects", "project"],
                physical_candidates=["projects"],
            ),
        }
    )


def test_build_dataset_jsonl_chat_format_and_minimum_count(tmp_path: Path) -> None:
    examples = build_dataset(_snapshot(), _aliases(), min_examples=500)

    assert len(examples) >= 500
    assert all(set(example) == {"messages"} for example in examples)
    assert all([message["role"] for example in examples for message in example["messages"]])
    assert all(example["messages"][0]["role"] == "system" for example in examples)
    assert all(example["messages"][-1]["role"] == "assistant" for example in examples)

    output = tmp_path / "db_agent_sft.jsonl"
    write_jsonl(examples, output)
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(examples)
    assert json.loads(lines[0])["messages"][0]["role"] == "system"


def test_dataset_validation_scans_sensitive_values() -> None:
    examples = build_dataset(_snapshot(), _aliases(), min_examples=500)
    report = validate_dataset(examples, min_examples=500, forbidden_values=["secret-password", "token-value"])

    assert report.valid is True
    assert report.sensitive_hits == []
    rendered = "\n".join(json.dumps(example, ensure_ascii=False) for example in examples)
    assert "secret-password" not in rendered
    assert "token-value" not in rendered
    assert "password" not in rendered
    assert "remember_token" not in rendered


def test_dataset_validation_rejects_sensitive_leaks() -> None:
    examples = [
        {
            "messages": [
                {"role": "system", "content": "safe"},
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "secret-password"},
            ]
        }
    ]

    report = validate_dataset(examples, min_examples=1, forbidden_values=["secret-password"])

    assert report.valid is False
    assert report.sensitive_hits == ["secret-password"]


def test_route_balance_and_required_smoke_question_coverage() -> None:
    examples = build_dataset(_snapshot(), _aliases(), min_examples=500)
    report = validate_dataset(examples, min_examples=500)

    assert report.valid is True
    assert report.route_counts["database_query"] >= 100
    assert report.route_counts["conversational"] >= 20
    assert report.route_counts["forbidden"] >= 20
    assert report.route_counts["clarification"] >= 20
    assert report.route_counts["unsupported"] >= 20
    assert report.route_counts["final_answer"] >= 20
    assert report.required_coverage["اعرض جميع اسماء المستخدمين"] is True
    assert report.required_coverage["اريد بيانات المستخدم Ayman Ibrahim El Sayed"] is True
    assert report.required_coverage["كام مشروع عندي؟"] is True
    assert report.required_coverage["انت كويس؟"] is True

