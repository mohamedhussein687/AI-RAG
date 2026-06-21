#!/usr/bin/env bash
set -euo pipefail
set -a
source /home/rag/.config/construction-rag/production.env
set +a
if [[ $# -ne 1 ]]; then echo "usage: sudo /home/rag/bin/restore.sh /home/rag/backups/<stamp>" >&2; exit 2; fi
src="$1"
[[ -f "$src/postgres.sql" && -f "$src/qdrant-storage.tgz" ]] || { echo "backup is incomplete" >&2; exit 1; }
cd /home/rag/current/construction-ai-rag-module
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml stop ai-module-api spring-gateway || true
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" < "$src/postgres.sql"
echo "Qdrant restore requires maintenance window: stop stack, replace /home/rag/data/qdrant from $src/qdrant-storage.tgz, then restart."
