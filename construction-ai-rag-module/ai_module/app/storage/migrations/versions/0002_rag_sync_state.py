"""add external rag sync metadata tables"""
from alembic import op
import sqlalchemy as sa

revision = "0002_rag_sync_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rag_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_table", sa.String(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "project_id", "source_name", "source_table", name="uq_rag_sync_state_source"),
    )
    for col in ("tenant_id", "project_id", "source_name", "source_table", "status"):
        op.create_index(f"ix_rag_sync_state_{col}", "rag_sync_state", [col])

    op.create_table(
        "rag_indexed_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_table", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(), nullable=False),
        sa.Column("document_hash", sa.String(), nullable=False),
        sa.Column("content_preview", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "project_id", "source_name", "source_table", "source_id", name="uq_rag_indexed_documents_source"),
    )
    for col in ("tenant_id", "project_id", "source_name", "source_table", "source_id", "qdrant_point_id", "document_hash", "is_active"):
        op.create_index(f"ix_rag_indexed_documents_{col}", "rag_indexed_documents", [col])


def downgrade():
    op.drop_table("rag_indexed_documents")
    op.drop_table("rag_sync_state")
