from sqlalchemy import Boolean, JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("tenant_id", "source_identity", "content_hash", "index_version", name="uq_document_identity_version"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String, index=True)
    source_identity: Mapped[str] = mapped_column(String, index=True)
    content_hash: Mapped[str] = mapped_column(String, index=True)
    index_version: Mapped[str] = mapped_column(String, index=True)
    access_policy: Mapped[dict] = mapped_column(JSON)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    indexed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String, index=True)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String, nullable=True)
    vector_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped[Document] = relationship(back_populates="chunks")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, index=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    query_summary: Mapped[str] = mapped_column(String)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    locale: Mapped[str] = mapped_column(String, default="ar")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentEvent(Base):
    __tablename__ = "agent_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    model_id: Mapped[str] = mapped_column(String)
    revision: Mapped[str] = mapped_column(String)
    serving_image: Mapped[str] = mapped_column(String)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagSyncState(Base):
    __tablename__ = "rag_sync_state"
    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "source_name", "source_table", name="uq_rag_sync_state_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    source_name: Mapped[str] = mapped_column(String, index=True)
    source_table: Mapped[str] = mapped_column(String, index=True)
    last_sync_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RagIndexedDocument(Base):
    __tablename__ = "rag_indexed_documents"
    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "source_name", "source_table", "source_id", name="uq_rag_indexed_documents_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    source_name: Mapped[str] = mapped_column(String, index=True)
    source_table: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    qdrant_point_id: Mapped[str] = mapped_column(String, index=True)
    document_hash: Mapped[str] = mapped_column(String, index=True)
    content_preview: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source_updated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
