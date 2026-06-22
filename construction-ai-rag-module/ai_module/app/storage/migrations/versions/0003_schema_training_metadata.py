"""add schema intelligence and training metadata tables"""
from alembic import op
import sqlalchemy as sa

revision = "0003_schema_training_metadata"
down_revision = "0002_rag_sync_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "schema_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("database_name", sa.String(), nullable=False),
        sa.Column("schema_hash", sa.String(), nullable=False),
        sa.Column("alias_hash", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("table_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relationship_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sensitive_field_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_name", "schema_hash", "alias_hash", name="uq_schema_snapshot_hash"),
    )
    for col in ("source_name", "database_name", "schema_hash", "alias_hash", "status"):
        op.create_index(f"ix_schema_snapshots_{col}", "schema_snapshots", [col])

    op.create_table(
        "schema_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("schema_hash", sa.String(), nullable=False),
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("column_names", sa.JSON(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_name", "schema_hash", "chunk_id", name="uq_schema_chunk_source_hash"),
    )
    for col in ("chunk_id", "source_name", "schema_hash", "table_name", "qdrant_point_id"):
        op.create_index(f"ix_schema_chunks_{col}", "schema_chunks", [col])

    op.create_table(
        "training_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("base_model", sa.String(), nullable=False),
        sa.Column("dataset_path", sa.String(), nullable=False),
        sa.Column("output_path", sa.String(), nullable=False),
        sa.Column("training_mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("resource_summary", sa.JSON(), nullable=False),
        sa.Column("metrics_summary", sa.JSON(), nullable=False),
        sa.Column("blocker", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for col in ("base_model", "training_mode", "status"):
        op.create_index(f"ix_training_runs_{col}", "training_runs", [col])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("evaluated_artifact", sa.String(), nullable=False),
        sa.Column("json_validity_rate", sa.String(), nullable=False),
        sa.Column("route_accuracy", sa.String(), nullable=False),
        sa.Column("table_resolution_accuracy", sa.String(), nullable=False),
        sa.Column("sensitive_refusal_rate", sa.String(), nullable=False),
        sa.Column("write_operation_rejection_rate", sa.String(), nullable=False),
        sa.Column("arabic_answer_score", sa.String(), nullable=False),
        sa.Column("smoke_prompt_results", sa.JSON(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])
    op.create_index("ix_evaluation_results_passed", "evaluation_results", ["passed"])


def downgrade():
    op.drop_table("evaluation_results")
    op.drop_table("training_runs")
    op.drop_table("schema_chunks")
    op.drop_table("schema_snapshots")
