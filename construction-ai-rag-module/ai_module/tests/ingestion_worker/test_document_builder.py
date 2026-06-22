from ingestion_worker.config import SourceConfig, TableConfig
from ingestion_worker.document_builder import build_document, normalize_content


def test_project_document_builder_is_stable_and_filters_sensitive_fields():
    source = SourceConfig(name="construction_mysql", tenant_id="orbit", project_id="default", tables=[])
    table = TableConfig(name="projects", primary_key="id", updated_at_column="updated_at", deleted_at_column="deleted_at", document_template="construction_project")
    row = {
        "id": 10,
        "title": "Test Project",
        "project_code": "C-1",
        "project_status": "active",
        "password": "must-not-render",
        "updated_at": "2026-06-22T10:00:00",
        "deleted_at": None,
    }

    first = build_document(source, table, row)
    second = build_document(source, table, row)

    assert first.document_hash == second.document_hash
    assert "Test Project" in first.content
    assert "active" in first.content
    assert "must-not-render" not in first.content
    assert first.metadata["source_identity"] == "construction_mysql:projects:10"
    assert first.metadata["source_status"] == "active"
    assert "status" not in first.metadata


def test_normalize_content_collapses_whitespace():
    assert normalize_content(" A   B \n\n C ") == "A B\nC"
