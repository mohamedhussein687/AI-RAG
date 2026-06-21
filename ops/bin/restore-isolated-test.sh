#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
  echo "usage: $0 /home/rag/backups/TIMESTAMP" >&2
  exit 2
fi
project="restore-test-$(date +%s)"
network="${project}-net"
postgres="${project}-postgres"
qdrant="${project}-qdrant"
cleanup() {
  docker rm -f "$postgres" "$qdrant" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker network create --internal "$network" >/dev/null
docker run -d --name "$postgres" --network "$network" -e POSTGRES_DB=restore_test -e POSTGRES_USER=restore_test -e POSTGRES_PASSWORD=restore_test postgres:16.6-bookworm >/dev/null
docker run -d --name "$qdrant" --network "$network" qdrant/qdrant:v1.12.5 >/dev/null
for _ in $(seq 1 30); do docker exec "$postgres" pg_isready -U restore_test -d restore_test >/dev/null 2>&1 && break; sleep 2; done
if [[ -f "$BACKUP_DIR/postgres.sql" ]]; then
  docker exec -i "$postgres" psql -U restore_test -d restore_test < "$BACKUP_DIR/postgres.sql" >/dev/null
elif [[ -f "$BACKUP_DIR/postgres.dump" ]]; then
  docker cp "$BACKUP_DIR/postgres.dump" "$postgres:/tmp/postgres.dump"
  docker exec "$postgres" pg_restore -U restore_test -d restore_test /tmp/postgres.dump >/dev/null
else
  echo "no postgres dump found in backup" >&2
  exit 3
fi
doc_count=$(docker exec "$postgres" psql -U restore_test -d restore_test -Atc "select count(*) from documents" 2>/dev/null || echo 0)
chunk_count=$(docker exec "$postgres" psql -U restore_test -d restore_test -Atc "select count(*) from document_chunks" 2>/dev/null || echo 0)
job_count=$(docker exec "$postgres" psql -U restore_test -d restore_test -Atc "select count(*) from ingestion_jobs" 2>/dev/null || echo 0)
printf 'restore_isolated=ok\ndocuments=%s\nchunks=%s\ningestion_jobs=%s\n' "$doc_count" "$chunk_count" "$job_count"
