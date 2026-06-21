#!/usr/bin/env bash
set -euo pipefail
cd /home/rag/current/construction-ai-rag-module
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml up -d --remove-orphans
timeout_seconds="${RAG_READY_TIMEOUT_SECONDS:-180}"
for _ in $(seq 1 "$timeout_seconds"); do
  if curl -fsS http://127.0.0.1:8080/health/ready >/dev/null 2>&1 && \
     curl -fsS http://127.0.0.1:8080/health/ready | grep -q '"status":"ok"'; then
    echo "gateway ready"
    exit 0
  fi
  sleep 1
done
echo "gateway did not become ready within ${timeout_seconds}s" >&2
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml ps >&2 || true
exit 1
