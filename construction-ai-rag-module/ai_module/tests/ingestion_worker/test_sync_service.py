from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ingestion_worker.config import SourceConfig, TableConfig
from ingestion_worker.sync import RagSyncService


class FakeEmbedder:
    async def embed(self, text):
        return [1.0, 0.0, 0.0]


class FakeQdrant:
    def __init__(self):
        self.upserts = []
        self.inactive = []

    async def upsert(self, point_id, vector, payload):
        self.upserts.append((point_id, vector, payload))

    async def mark_inactive(self, point_ids):
        self.inactive.extend(point_ids)


def make_service(existing=None):
    service = object.__new__(RagSyncService)
    service.settings = SimpleNamespace(max_chunk_chars=1600, index_version="v-test")
    service.embedder = FakeEmbedder()
    service.qdrant = FakeQdrant()
    service._existing = existing
    return service


@pytest.mark.asyncio
async def test_sync_row_skips_unchanged_document(monkeypatch):
    source, table = _source_table()
    row = {"id": 1, "title": "A", "updated_at": datetime(2026, 6, 22, tzinfo=UTC), "deleted_at": None}
    service = make_service()
    doc_hash = None

    async def existing(source_arg, table_arg, source_id, session=None):
        return SimpleNamespace(is_active=True, document_hash=doc_hash)

    from ingestion_worker.document_builder import build_document

    doc_hash = build_document(source, table, row).document_hash
    service._existing_document = existing

    result = await RagSyncService._sync_row(service, source, table, row, dry_run=False)

    assert result == "skipped"
    assert service.qdrant.upserts == []


@pytest.mark.asyncio
async def test_full_sync_can_force_reindex_same_hash(monkeypatch):
    source, table = _source_table()
    row = {"id": 1, "title": "A", "updated_at": datetime(2026, 6, 22, tzinfo=UTC), "deleted_at": None}
    service = make_service()
    stored = {}

    from ingestion_worker.document_builder import build_document

    doc_hash = build_document(source, table, row).document_hash

    async def existing(source_arg, table_arg, source_id, session=None):
        return SimpleNamespace(is_active=True, document_hash=doc_hash)

    async def index_document(source_arg, table_arg, source_id, point_id, document):
        stored["source_id"] = source_id

    service._existing_document = existing
    service._index_document = index_document

    result = await RagSyncService._sync_row(service, source, table, row, dry_run=False, force_reindex=True)

    assert result == "indexed"
    assert stored["source_id"] == "1"


@pytest.mark.asyncio
async def test_sync_row_marks_soft_deleted_inactive(monkeypatch):
    source, table = _source_table()
    row = {"id": 1, "title": "A", "updated_at": datetime(2026, 6, 22, tzinfo=UTC), "deleted_at": datetime(2026, 6, 22, tzinfo=UTC)}
    service = make_service()

    async def mark_inactive(source_arg, table_arg, source_id, point_id):
        service.qdrant.inactive.append(point_id)

    service._mark_inactive = mark_inactive

    result = await RagSyncService._sync_row(service, source, table, row, dry_run=False)

    assert result == "deleted"
    assert service.qdrant.inactive


@pytest.mark.asyncio
async def test_sync_row_upserts_changed_document(monkeypatch):
    source, table = _source_table()
    row = {"id": 1, "title": "A", "updated_at": datetime(2026, 6, 22, tzinfo=UTC), "deleted_at": None}
    service = make_service()
    stored = {}

    async def existing(source_arg, table_arg, source_id, session=None):
        return None

    async def index_document(source_arg, table_arg, source_id, point_id, document):
        stored["source_id"] = source_id
        stored["point_id"] = point_id
        stored["hash"] = document.document_hash

    service._existing_document = existing
    service._index_document = index_document

    result = await RagSyncService._sync_row(service, source, table, row, dry_run=False)

    assert result == "indexed"
    assert stored["source_id"] == "1"
    assert stored["point_id"]
    assert stored["hash"]


def _source_table():
    source = SourceConfig(name="construction_mysql", tenant_id="orbit", project_id="default", tables=[])
    table = TableConfig(name="projects", primary_key="id", updated_at_column="updated_at", deleted_at_column="deleted_at", document_template="construction_project")
    return source, table
