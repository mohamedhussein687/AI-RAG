# Phase 1 MySQL-to-RAG Ingestion Runbook

This runbook prepares and verifies the Phase 1 polling ingestion pipeline:

```text
External MySQL -> ingestion-worker -> embedding service -> Qdrant -> PostgreSQL sync metadata -> RAG search
```

Phase 1 uses `updated_at` and `deleted_at` polling. It does not use Kafka, Debezium, or model fine-tuning.

## Version Pins

- Qdrant server: `qdrant/qdrant:v1.12.5`
- Python client: `qdrant-client==1.12.1`

Keep Qdrant server/client on the same minor line unless a compatibility test has been run.

## Required MySQL Read-Only User

Create a dedicated MySQL user with the minimum read-only grants needed for configured source tables and schema metadata:

```sql
CREATE USER 'rag_reader'@'RAG_SERVER_IP' IDENTIFIED BY 'STRONG_PASSWORD';
GRANT SELECT ON construction_db.projects TO 'rag_reader'@'RAG_SERVER_IP';
GRANT SELECT ON construction_db.tasks TO 'rag_reader'@'RAG_SERVER_IP';
GRANT SELECT ON construction_db.clients TO 'rag_reader'@'RAG_SERVER_IP';
GRANT SELECT ON information_schema.columns TO 'rag_reader'@'RAG_SERVER_IP';
FLUSH PRIVILEGES;
```

Do not grant `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRIGGER`, or administrative privileges.

Store the password only in the protected production environment file:

```text
/home/rag/.config/construction-rag/production.env
```

Never commit or print this password.

## Required Source Tables and Columns

Tables are configured in:

```text
construction-ai-rag-module/ai_module/config/rag_sources.yml
```

The initial source is `construction_mysql` with:

- `projects`
- `tasks`
- `clients`

Each configured table must have:

- a stable primary key column, usually `id`
- an `updated_at` column that changes whenever indexed content changes
- a nullable `deleted_at` column for soft deletes

If a table does not support soft deletes, set `deleted_at_column` to an empty value only after confirming deletes are handled outside RAG.

The worker reads all columns from each configured table, excludes sensitive names during generic document rendering, and converts rows into Arabic/English searchable documents.

## Environment Variables

Required ingestion variables:

```bash
MYSQL_HOST=...
MYSQL_PORT=3306
MYSQL_DATABASE=...
MYSQL_USERNAME=rag_reader
MYSQL_PASSWORD=...
MYSQL_CONNECT_TIMEOUT_SECONDS=10
RAG_SOURCES_CONFIG=config/rag_sources.yml
INGESTION_INTERVAL_SECONDS=60
```

The worker also requires existing production variables for:

- `POSTGRES_URL`
- `QDRANT_URL`
- `QDRANT_COLLECTION`
- embedding service settings
- `INDEX_VERSION`

## Deploy Migration

Run migrations from the active release through Docker Compose so secrets stay inside the protected environment file:

```bash
cd /home/rag/current
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml run --rm ai-module-api python -m alembic upgrade head
```

## First Full Import

Run a dry run first:

```bash
cd /home/rag/current
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml run --rm ingestion-worker \
  python -m ingestion_worker sync --source construction_mysql --mode full --dry-run
```

Run the full import:

```bash
cd /home/rag/current
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml run --rm ingestion-worker \
  python -m ingestion_worker sync --source construction_mysql --mode full
```

Full import intentionally reindexes configured rows even if hashes match. Use this to repair payload format changes or rebuild a collection after backup/restore.

## Start Incremental Worker Loop

The production compose service is private and exposes no ports.

Start the worker profile:

```bash
cd /home/rag/current
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml --profile worker up -d ingestion-worker
```

One-shot incremental sync:

```bash
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml run --rm ingestion-worker \
  python -m ingestion_worker sync --source construction_mysql --mode incremental
```

## Health and Status

Show last successful sync, last error, active indexed counts, and inactive counts:

```bash
cd /home/rag/current
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml run --rm ingestion-worker \
  python -m ingestion_worker status --source construction_mysql
```

JSON output:

```bash
python -m ingestion_worker status --source construction_mysql --json
```

Expected fields per table:

- `last_sync_at`
- `last_success_at`
- `status`
- `last_error`
- `indexed_documents`
- `inactive_documents`

## Verify PostgreSQL

Run from the PostgreSQL container:

```bash
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml exec -T postgres \
  bash -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select source_table, status, last_success_at, error_message from rag_sync_state order by source_table;"'
```

```bash
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml exec -T postgres \
  bash -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select source_table, count(*) filter (where is_active) active, count(*) filter (where not is_active) inactive from rag_indexed_documents group by source_table;"'
```

## Verify Qdrant

Qdrant is private on the Docker network. Inspect from a container on that network:

```bash
sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
  -f docker-compose.prod.yml exec -T ai-module-api \
  python - <<'PY'
from app.config import get_settings
from qdrant_client import QdrantClient
s = get_settings()
c = QdrantClient(url=s.qdrant_url)
print(c.count(collection_name=s.qdrant_collection, exact=True))
PY
```

Payloads must include:

- `tenant_id`
- `project_id`
- `source_table`
- `source_id`
- `status=indexed`
- `is_active=true`

Soft-deleted rows are kept for audit but payload-marked:

- `status=deleted`
- `is_active=false`

Search filters require `is_active=true`, so inactive rows are not returned.

## Verify RAG Search

Use the private AI module endpoint from inside the stack or the public Spring Gateway flow. The RAG search request must include the expected tenant/project:

```bash
curl -X POST http://ai-module-api:8000/api/rag/search \
  -H "Authorization: Bearer $AI_MODULE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "معلومات عن مشروع تجريبي",
    "user_context": {
      "id": "operator-check",
      "tenant_id": "orbit",
      "project_ids": ["default"],
      "permissions": ["rag:read"]
    },
    "top_k": 5,
    "filters": {"project_id": "default"}
  }'
```

Confirm:

- expected project/client/task content appears
- another tenant returns no results
- soft-deleted rows do not appear

## Rollback and Reindex Procedure

Rollback application release:

```bash
sudo /home/rag/bin/rollback.sh /home/rag/releases/<PREVIOUS_SHA>
```

This does not automatically reverse metadata rows or Qdrant points.

If a bad import wrote incorrect payloads:

1. Stop worker loop:
   ```bash
   cd /home/rag/current
   sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
     -f docker-compose.prod.yml stop ingestion-worker
   ```
2. Roll back the application release if needed.
3. Restore PostgreSQL/Qdrant from backup if incorrect vectors must be removed.
4. Otherwise run a full import from the fixed release to repair payloads:
   ```bash
   sudo docker compose --env-file /home/rag/.config/construction-rag/production.env \
     -f docker-compose.prod.yml run --rm ingestion-worker \
     python -m ingestion_worker sync --source construction_mysql --mode full
   ```
5. Verify status, counts, Qdrant payloads, and RAG search.
6. Restart worker loop.

## Future CDC Extension Point

Future Debezium/Kafka CDC should reuse:

- `DocumentBuilder`
- stable document hash
- deterministic Qdrant point IDs
- `rag_indexed_documents`
- active/inactive payload semantics

CDC events should feed the same row-level indexing path instead of introducing a separate vector-writing implementation.
