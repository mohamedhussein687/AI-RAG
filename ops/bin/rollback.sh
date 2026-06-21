#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "usage: sudo /home/rag/bin/rollback.sh /home/rag/releases/<sha>" >&2; exit 2; fi
target="$1"
[[ -d "$target" ]] || { echo "release not found: $target" >&2; exit 1; }
previous="$(readlink -f /home/rag/current)"
ln -sfn "$target" /home/rag/current
chown -h rag:rag /home/rag/current
cd /home/rag/current/construction-ai-rag-module
if ! docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml up -d --remove-orphans; then
  ln -sfn "$previous" /home/rag/current
  chown -h rag:rag /home/rag/current
  echo "rollback activation failed; restored current symlink to $previous" >&2
  exit 1
fi
timeout_seconds="${RAG_READY_TIMEOUT_SECONDS:-180}"
for _ in $(seq 1 "$timeout_seconds"); do
  if curl -fsS http://127.0.0.1:8080/health/ready >/dev/null 2>&1 && \
     curl -fsS http://127.0.0.1:8080/health/ready | grep -q '"status":"ok"'; then
    echo "rollback ready: $target"
    exit 0
  fi
  sleep 1
done
ln -sfn "$previous" /home/rag/current
chown -h rag:rag /home/rag/current
echo "rollback target did not become ready within ${timeout_seconds}s; restored current symlink to $previous" >&2
cd /home/rag/current/construction-ai-rag-module
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml up -d --remove-orphans >/dev/null 2>&1 || true
exit 1
