from app.schema.schema_ingestion import build_schema_chunks
from app.schema.schema_models import AliasCatalog, AliasEntry, SchemaColumn, SchemaSnapshot, SchemaTable
from app.schema.schema_search import search_schema_chunks


def test_schema_chunk_generation_excludes_sensitive_columns_and_includes_aliases():
    snapshot = SchemaSnapshot(
        source_name="construction_mysql",
        database_name="db",
        schema_hash="hash1",
        tables=[
            SchemaTable(
                name="users",
                classification="business",
                columns=[
                    SchemaColumn(name="id", data_type="int", is_primary_key=True),
                    SchemaColumn(name="name", data_type="varchar", safe_sample_values=["Basma"]),
                    SchemaColumn(name="password", data_type="varchar"),
                ],
            )
        ],
    )
    aliases = AliasCatalog(aliases={"users": AliasEntry(arabic=["المستخدمين"], english=["users"], physical_candidates=["users"])})

    chunks = build_schema_chunks(snapshot, aliases)

    assert len(chunks) == 1
    assert chunks[0].table_name == "users"
    assert "المستخدمين" in chunks[0].content
    assert "password" in chunks[0].content
    assert "Basma" in chunks[0].content
    assert chunks[0].metadata["sensitive_columns"] == ["password"]


def test_schema_search_returns_relevant_chunks_with_metadata_filters():
    snapshot = SchemaSnapshot(
        source_name="construction_mysql",
        database_name="db",
        schema_hash="hash1",
        tables=[
            SchemaTable(name="users", columns=[SchemaColumn(name="name", data_type="varchar")]),
            SchemaTable(name="projects", columns=[SchemaColumn(name="project_status", data_type="varchar")]),
        ],
    )
    chunks = build_schema_chunks(snapshot, AliasCatalog())

    results = search_schema_chunks(chunks, query="اسماء المستخدمين users", source_name="construction_mysql", top_k=1)

    assert len(results) == 1
    assert results[0].table_name == "users"
