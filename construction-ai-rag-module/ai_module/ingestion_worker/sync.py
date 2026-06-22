from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.rag.embedding_client import EmbeddingClient
from app.rag.qdrant_service import get_qdrant_service
from app.storage.models import RagIndexedDocument, RagSyncState
from app.storage.postgres import create_session_factory
from ingestion_worker.config import SourceConfig, TableConfig, load_sources, source_by_name, table_by_name
from ingestion_worker.document_builder import BuiltDocument, build_document
from ingestion_worker.ids import deterministic_point_id
from ingestion_worker.mysql_source import MySqlSource

log = logging.getLogger(__name__)


@dataclass
class SyncStats:
    source: str
    table: str
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: int = 0


@dataclass
class TableStatus:
    source: str
    table: str
    tenant_id: str
    project_id: str
    last_sync_at: datetime | None
    last_success_at: datetime | None
    status: str
    last_error: str | None
    indexed_documents: int
    inactive_documents: int


class RagSyncService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.session_factory = create_session_factory(self.settings)
        self.embedder = EmbeddingClient(self.settings)
        self.qdrant = get_qdrant_service(self.settings)

    async def sync_configured(self, *, source_name: str | None, table_name: str | None, mode: str, dry_run: bool) -> list[SyncStats]:
        sources = source_by_name(load_sources(self.settings.rag_sources_config), source_name)
        results: list[SyncStats] = []
        async with MySqlSource(self.settings) as mysql:
            for source in sources:
                for table in table_by_name(source, table_name):
                    results.append(await self.sync_table(mysql, source, table, mode=mode, dry_run=dry_run))
        return results

    async def status(self, *, source_name: str | None, table_name: str | None) -> list[TableStatus]:
        sources = source_by_name(load_sources(self.settings.rag_sources_config), source_name)
        results: list[TableStatus] = []
        async with self.session_factory() as session:
            for source in sources:
                for table in table_by_name(source, table_name):
                    state = (await session.execute(_sync_state_stmt(source, table))).scalar_one_or_none()
                    indexed = (
                        await session.execute(
                            select(func.count(RagIndexedDocument.id)).where(
                                RagIndexedDocument.tenant_id == source.tenant_id,
                                RagIndexedDocument.project_id == source.project_id,
                                RagIndexedDocument.source_name == source.name,
                                RagIndexedDocument.source_table == table.name,
                                RagIndexedDocument.is_active.is_(True),
                            )
                        )
                    ).scalar_one()
                    inactive = (
                        await session.execute(
                            select(func.count(RagIndexedDocument.id)).where(
                                RagIndexedDocument.tenant_id == source.tenant_id,
                                RagIndexedDocument.project_id == source.project_id,
                                RagIndexedDocument.source_name == source.name,
                                RagIndexedDocument.source_table == table.name,
                                RagIndexedDocument.is_active.is_(False),
                            )
                        )
                    ).scalar_one()
                    results.append(
                        TableStatus(
                            source=source.name,
                            table=table.name,
                            tenant_id=source.tenant_id,
                            project_id=source.project_id,
                            last_sync_at=state.last_sync_at if state else None,
                            last_success_at=state.last_success_at if state else None,
                            status=state.status if state else "never_run",
                            last_error=state.error_message if state else None,
                            indexed_documents=int(indexed),
                            inactive_documents=int(inactive),
                        )
                    )
        return results

    async def sync_table(self, mysql: MySqlSource, source: SourceConfig, table: TableConfig, *, mode: str, dry_run: bool) -> SyncStats:
        stats = SyncStats(source=source.name, table=table.name)
        sync_started_at = datetime.now(UTC)
        since = None if mode == "full" else await self._last_sync_at(source, table)
        await self._set_sync_state(source, table, status="processing", last_sync_at=sync_started_at, error_message=None, dry_run=dry_run)
        try:
            async for rows in mysql.iter_rows(table, since=since):
                for row in rows:
                    stats.scanned += 1
                    try:
                        result = await self._sync_row(source, table, row, dry_run=dry_run, force_reindex=mode == "full")
                    except Exception as exc:
                        stats.errors += 1
                        log.exception(
                            "rag_sync_row_failed source=%s table=%s source_id=%s error=%s",
                            source.name,
                            table.name,
                            _safe_source_id(table, row),
                            type(exc).__name__,
                        )
                        continue
                    if result == "indexed":
                        stats.indexed += 1
                    elif result == "deleted":
                        stats.deleted += 1
                    elif result == "skipped":
                        stats.skipped += 1
            status = "failed" if stats.errors else "success"
            error_message = f"{stats.errors} row errors" if stats.errors else None
            await self._set_sync_state(source, table, status=status, last_sync_at=sync_started_at, last_success_at=sync_started_at if not stats.errors else None, error_message=error_message, dry_run=dry_run)
        except Exception as exc:
            await self._set_sync_state(source, table, status="failed", last_sync_at=sync_started_at, error_message=type(exc).__name__, dry_run=dry_run)
            raise
        log.info(
            "rag_sync_complete source=%s table=%s mode=%s dry_run=%s scanned=%s indexed=%s skipped=%s deleted=%s errors=%s",
            source.name,
            table.name,
            mode,
            dry_run,
            stats.scanned,
            stats.indexed,
            stats.skipped,
            stats.deleted,
            stats.errors,
        )
        return stats

    async def _sync_row(self, source: SourceConfig, table: TableConfig, row: dict[str, Any], *, dry_run: bool, force_reindex: bool = False) -> str:
        source_id = str(row[table.primary_key])
        deleted = bool(table.deleted_at_column and row.get(table.deleted_at_column) is not None)
        point_id = deterministic_point_id(source.tenant_id, source.project_id, table.name, source_id)
        if deleted:
            if not dry_run:
                await self._mark_inactive(source, table, source_id, point_id)
            return "deleted"

        document = build_document(source, table, row)
        existing = await self._existing_document(source, table, source_id)
        if not force_reindex and existing and existing.is_active and existing.document_hash == document.document_hash:
            return "skipped"
        if dry_run:
            return "indexed"
        await self._index_document(source, table, source_id, point_id, document)
        return "indexed"

    async def _index_document(self, source: SourceConfig, table: TableConfig, source_id: str, point_id: str, document: BuiltDocument) -> None:
        vector = await self.embedder.embed(document.content)
        payload = {
            "tenant_id": source.tenant_id,
            "project_id": source.project_id,
            "document_id": f"{source.name}:{table.name}:{source_id}",
            "document_version": self.settings.index_version,
            "title": document.title,
            "source_type": table.name,
            "permissions": ["rag:read"],
            "access_groups": [],
            "status": "indexed",
            "is_active": True,
            "index_version": self.settings.index_version,
            "chunk_index": 0,
            "page_number": None,
            "section_title": table.document_template,
            "chunk_id": point_id,
            "text": document.content[: self.settings.max_chunk_chars],
            "content_hash": document.document_hash,
            **document.metadata,
        }
        await self.qdrant.upsert(point_id, vector, payload)
        async with self.session_factory() as session:
            existing = await self._existing_document(source, table, source_id, session=session)
            now = datetime.now(UTC)
            if existing:
                existing.qdrant_point_id = point_id
                existing.document_hash = document.document_hash
                existing.content_preview = document.content_preview
                existing.is_active = True
                existing.source_updated_at = _source_updated_at(document)
                existing.indexed_at = now
            else:
                session.add(
                    RagIndexedDocument(
                        tenant_id=source.tenant_id,
                        project_id=source.project_id,
                        source_name=source.name,
                        source_table=table.name,
                        source_id=source_id,
                        qdrant_point_id=point_id,
                        document_hash=document.document_hash,
                        content_preview=document.content_preview,
                        is_active=True,
                        source_updated_at=_source_updated_at(document),
                        indexed_at=now,
                    )
                )
            await session.commit()

    async def _mark_inactive(self, source: SourceConfig, table: TableConfig, source_id: str, point_id: str) -> None:
        # We mark inactive in Qdrant instead of deleting so historical source state remains auditable.
        await self.qdrant.mark_inactive([point_id])
        async with self.session_factory() as session:
            existing = await self._existing_document(source, table, source_id, session=session)
            if existing:
                existing.is_active = False
                await session.commit()

    async def _existing_document(self, source: SourceConfig, table: TableConfig, source_id: str, session=None) -> RagIndexedDocument | None:
        stmt = select(RagIndexedDocument).where(
            RagIndexedDocument.tenant_id == source.tenant_id,
            RagIndexedDocument.project_id == source.project_id,
            RagIndexedDocument.source_name == source.name,
            RagIndexedDocument.source_table == table.name,
            RagIndexedDocument.source_id == source_id,
        )
        if session is not None:
            return (await session.execute(stmt)).scalar_one_or_none()
        async with self.session_factory() as owned_session:
            return (await owned_session.execute(stmt)).scalar_one_or_none()

    async def _last_sync_at(self, source: SourceConfig, table: TableConfig) -> datetime | None:
        async with self.session_factory() as session:
            state = (await session.execute(_sync_state_stmt(source, table))).scalar_one_or_none()
            return state.last_success_at if state else None

    async def _set_sync_state(
        self,
        source: SourceConfig,
        table: TableConfig,
        *,
        status: str,
        last_sync_at: datetime | None = None,
        last_success_at: datetime | None = None,
        error_message: str | None = None,
        dry_run: bool,
    ) -> None:
        if dry_run:
            return
        async with self.session_factory() as session:
            state = (await session.execute(_sync_state_stmt(source, table))).scalar_one_or_none()
            if not state:
                state = RagSyncState(tenant_id=source.tenant_id, project_id=source.project_id, source_name=source.name, source_table=table.name, status=status)
                session.add(state)
            state.status = status
            state.error_message = error_message
            if last_sync_at is not None:
                state.last_sync_at = last_sync_at
            if last_success_at is not None:
                state.last_success_at = last_success_at
            await session.commit()


async def run_loop(*, interval: int, source_name: str | None, dry_run: bool) -> None:
    service = RagSyncService()
    while True:
        try:
            await service.sync_configured(source_name=source_name, table_name=None, mode="incremental", dry_run=dry_run)
        except Exception as exc:
            log.exception("rag_sync_loop_failed error=%s", type(exc).__name__)
        await asyncio.sleep(interval)


def _sync_state_stmt(source: SourceConfig, table: TableConfig):
    return select(RagSyncState).where(
        RagSyncState.tenant_id == source.tenant_id,
        RagSyncState.project_id == source.project_id,
        RagSyncState.source_name == source.name,
        RagSyncState.source_table == table.name,
    )


def _source_updated_at(document: BuiltDocument) -> datetime | None:
    value = document.metadata.get("source_updated_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _safe_source_id(table: TableConfig, row: dict[str, Any]) -> str:
    return str(row.get(table.primary_key, "unknown"))
