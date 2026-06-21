#!/usr/bin/env bash
set -euo pipefail
set -a
source /home/rag/.config/construction-rag/production.env
set +a
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="/home/rag/backups/$stamp"
mkdir -p "$dest"
cd /home/rag/current/construction-ai-rag-module
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$dest/postgres.sql"
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml exec -T qdrant bash -lc 'tar -C /qdrant/storage -czf - .' > "$dest/qdrant-storage.tgz"
readlink -f /home/rag/current > "$dest/current-release.txt"
{ echo "created_at=$stamp"; echo "models recorded in production.env with revisions redacted from secrets"; } > "$dest/metadata.txt"
chmod -R go-rwx "$dest"
echo "$dest"
