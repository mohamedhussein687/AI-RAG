"""initial ai rag metadata tables"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_identity", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("index_version", sa.String(), nullable=False),
        sa.Column("access_policy", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "source_identity", "content_hash", "index_version", name="uq_document_identity_version"))
    for col in ("tenant_id", "project_id", "source_type", "content_hash", "index_version", "status"):
        op.create_index(f"ix_documents_{col}", "documents", [col])

    op.create_table("document_chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(), nullable=True),
        sa.Column("vector_id", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"))
    for col in ("document_id", "tenant_id", "project_id", "text_hash", "source_type", "vector_id"):
        op.create_index(f"ix_document_chunks_{col}", "document_chunks", [col])

    op.create_table("ingestion_jobs", sa.Column("id", sa.String(), primary_key=True), sa.Column("document_id", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("error_message", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])
    op.create_table("retrieval_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("request_id", sa.String(), nullable=False), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("query_summary", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_retrieval_logs_request_id", "retrieval_logs", ["request_id"])
    op.create_index("ix_retrieval_logs_tenant_id", "retrieval_logs", ["tenant_id"])
    op.create_table("conversations", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=True), sa.Column("locale", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_table("agent_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("request_id", sa.String(), nullable=False), sa.Column("conversation_id", sa.String(), nullable=True), sa.Column("tenant_id", sa.String(), nullable=True), sa.Column("event_type", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("summary", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    for col in ("request_id", "tenant_id", "event_type", "status"):
        op.create_index(f"ix_agent_events_{col}", "agent_events", [col])
    op.create_table("model_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("kind", sa.String(), nullable=False), sa.Column("model_id", sa.String(), nullable=False), sa.Column("revision", sa.String(), nullable=False), sa.Column("serving_image", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_model_versions_kind", "model_versions", ["kind"])


def downgrade():
    for table in ["model_versions", "agent_events", "conversations", "retrieval_logs", "ingestion_jobs", "document_chunks", "documents"]:
        op.drop_table(table)
