import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select

from app.config import Settings
from app.schemas import DocumentIndexRequest, DocumentIndexResponse, RagChunk
from app.storage.models import Document, DocumentChunk, IngestionJob
from app.storage.postgres import create_session_factory

from .chunking_service import ChunkingService
from .embedding_client import EmbeddingClient
from .ingestion_service import IngestionService
from .qdrant_service import get_qdrant_service, qdrant


@dataclass
class StoredDocument:
    id: str
    tenant_id: str
    project_id: str | None
    title: str
    source_type: str
    access_policy: dict[str, Any]
    metadata: dict[str, Any]
    content_hash: str
    status: str = "pending"


documents: dict[str, StoredDocument] = {}
chunks: dict[str, RagChunk] = {}
chunk_payloads: dict[str, dict] = {}


class DocumentService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chunker = ChunkingService(settings.max_chunk_chars)
        self.embedder = EmbeddingClient(settings)
        self.ingestion = IngestionService(settings)
        self.vector_store = get_qdrant_service(settings)

    async def index(self, request: DocumentIndexRequest) -> DocumentIndexResponse:
        if self.settings.production_mode:
            return await self._index_production(request)
        return await self._index_in_memory(request)

    async def _index_production(self, request: DocumentIndexRequest) -> DocumentIndexResponse:
        pieces = self.chunker.split(request.content)
        if not pieces:
            raise ValueError("document content produced no chunks")
        clean = self.chunker.clean_text(request.content)
        content_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        source_identity = str(request.metadata.get("source_identity") or request.metadata.get("source_id") or request.title)
        doc_id = stable_id("doc", request.tenant_id, source_identity, content_hash, self.settings.index_version)
        job_id = stable_id("job", doc_id, self.settings.index_version)
        session_factory = create_session_factory(self.settings)

        async with session_factory() as session:
            existing = await session.get(Document, doc_id)
            if existing and existing.status == "indexed":
                count = (await session.execute(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc_id))).scalar_one()
                return DocumentIndexResponse(document_id=doc_id, status="indexed", chunks_indexed=count)
            if not existing:
                session.add(Document(
                    id=doc_id,
                    tenant_id=request.tenant_id,
                    project_id=request.project_id,
                    title=request.title,
                    source_type=request.source_type,
                    source_identity=source_identity,
                    content_hash=content_hash,
                    index_version=self.settings.index_version,
                    access_policy=request.access_policy.model_dump(),
                    metadata_json=request.metadata,
                    status="pending",
                ))
            session.add(IngestionJob(id=job_id, document_id=doc_id, status="pending"))
            await session.commit()

        async def work() -> int:
            vectors = await self.embedder.embed_batch(pieces)
            points: list[tuple[str, list[float], dict[str, Any]]] = []
            db_chunks: list[DocumentChunk] = []
            permissions = request.access_policy.permissions
            for idx, (text, vector) in enumerate(zip(pieces, vectors, strict=True)):
                excerpt = text[: self.settings.max_chunk_chars]
                text_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
                chunk_id = stable_id("chk", doc_id, str(idx), text_hash)
                payload = {
                    "tenant_id": request.tenant_id,
                    "project_id": request.project_id,
                    "document_id": doc_id,
                    "document_version": request.metadata.get("version", self.settings.index_version),
                    "title": request.title,
                    "source_type": request.source_type,
                    "permissions": permissions,
                    "access_groups": request.metadata.get("access_groups", []),
                    "status": "indexed",
                    "index_version": self.settings.index_version,
                    "chunk_index": idx,
                    "page_number": None,
                    "section_title": None,
                    "chunk_id": chunk_id,
                    "text": excerpt,
                    "content_hash": content_hash,
                }
                points.append((chunk_id, vector, payload))
                db_chunks.append(DocumentChunk(
                    id=chunk_id,
                    document_id=doc_id,
                    tenant_id=request.tenant_id,
                    project_id=request.project_id,
                    chunk_index=idx,
                    text=excerpt,
                    text_hash=text_hash,
                    title=request.title,
                    source_type=request.source_type,
                    permissions=permissions,
                    page_number=None,
                    section_title=None,
                    vector_id=chunk_id,
                    payload=payload,
                ))
            async with session_factory() as session:
                doc = await session.get(Document, doc_id)
                if doc is None:
                    raise RuntimeError("document disappeared during indexing")
                doc.status = "processing"
                await session.commit()
            await self.vector_store.upsert_many(points)
            async with session_factory() as session:
                doc = await session.get(Document, doc_id)
                session.add_all(db_chunks)
                doc.status = "indexed"
                doc.indexed_at = func.now()
                job = await session.get(IngestionJob, job_id)
                if job:
                    job.status = "indexed"
                await session.commit()
            return len(db_chunks)

        try:
            indexed = await self.ingestion.run_indexing_job(job_id, doc_id, work)
        except Exception as exc:
            async with session_factory() as session:
                doc = await session.get(Document, doc_id)
                if doc:
                    doc.status = "failed"
                    doc.error_message = type(exc).__name__
                job = await session.get(IngestionJob, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = type(exc).__name__
                await session.commit()
            raise
        return DocumentIndexResponse(document_id=doc_id, status="indexed", chunks_indexed=indexed)

    async def _index_in_memory(self, request: DocumentIndexRequest) -> DocumentIndexResponse:
        pieces = self.chunker.split(request.content)
        if not pieces:
            raise ValueError("document content produced no chunks")
        content_hash = hashlib.sha256(self.chunker.clean_text(request.content).encode("utf-8")).hexdigest()
        source_identity = str(request.metadata.get("source_identity") or request.metadata.get("source_id") or request.title)
        doc_id = stable_id("doc", request.tenant_id, source_identity, content_hash, self.settings.index_version)
        job_id = stable_id("job", doc_id, self.settings.index_version)

        async def work() -> int:
            created_chunk_ids: list[str] = []
            try:
                vectors = await self.embedder.embed_batch(pieces)
                for idx, (text, vector) in enumerate(zip(pieces, vectors, strict=True)):
                    excerpt = text[: self.settings.max_chunk_chars]
                    chunk_id = stable_id("chk", doc_id, str(idx), hashlib.sha256(excerpt.encode("utf-8")).hexdigest())
                    chunk = RagChunk(chunk_id=chunk_id, document_id=doc_id, title=request.title, source_type=request.source_type, project_id=request.project_id, chunk_index=idx, page_number=None, section_title=None, text=excerpt, score=None)
                    payload = {"tenant_id": request.tenant_id, "project_id": request.project_id, "document_id": doc_id, "document_version": request.metadata.get("version", self.settings.index_version), "title": request.title, "source_type": request.source_type, "permissions": request.access_policy.permissions, "access_groups": request.metadata.get("access_groups", []), "status": "indexed", "index_version": self.settings.index_version, "chunk_index": idx, "page_number": None, "section_title": None, "chunk_id": chunk_id, "text": excerpt, "content_hash": content_hash}
                    await qdrant.upsert(chunk_id, vector, payload)
                    chunks[chunk_id] = chunk
                    chunk_payloads[chunk_id] = payload
                    created_chunk_ids.append(chunk_id)
            except Exception:
                for chunk_id in created_chunk_ids:
                    chunks.pop(chunk_id, None)
                    chunk_payloads.pop(chunk_id, None)
                    qdrant.points.pop(chunk_id, None)
                raise
            return len(pieces)

        documents[doc_id] = StoredDocument(id=doc_id, tenant_id=request.tenant_id, project_id=request.project_id, title=request.title, source_type=request.source_type, access_policy=request.access_policy.model_dump(), metadata=request.metadata, content_hash=content_hash)
        indexed = await self.ingestion.run_indexing_job(job_id, doc_id, work)
        documents[doc_id].status = "indexed"
        return DocumentIndexResponse(document_id=doc_id, status="indexed", chunks_indexed=indexed)


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"
