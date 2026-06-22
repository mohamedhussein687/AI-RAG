from app.schema.schema_hash import calculate_schema_hash
from app.schema.schema_models import AliasCatalog, AliasEntry, SchemaColumn, SchemaSnapshot, SchemaTable


def test_schema_hash_changes_when_columns_change():
    base = SchemaSnapshot(
        source_name="construction_mysql",
        database_name="db",
        schema_hash="pending",
        tables=[SchemaTable(name="users", columns=[SchemaColumn(name="id", data_type="int")])],
    )
    changed = SchemaSnapshot(
        source_name="construction_mysql",
        database_name="db",
        schema_hash="pending",
        tables=[SchemaTable(name="users", columns=[SchemaColumn(name="id", data_type="int"), SchemaColumn(name="name", data_type="varchar")])],
    )

    assert calculate_schema_hash(base) != calculate_schema_hash(changed)


def test_schema_hash_includes_alias_hash():
    snapshot = SchemaSnapshot(
        source_name="construction_mysql",
        database_name="db",
        schema_hash="pending",
        tables=[SchemaTable(name="users", columns=[SchemaColumn(name="id", data_type="int")])],
    )
    users_alias = AliasCatalog(aliases={"users": AliasEntry(arabic=["المستخدمين"], physical_candidates=["users"])})
    employees_alias = AliasCatalog(aliases={"users": AliasEntry(arabic=["الموظفين"], physical_candidates=["users"])})

    assert calculate_schema_hash(snapshot, users_alias) != calculate_schema_hash(snapshot, employees_alias)
