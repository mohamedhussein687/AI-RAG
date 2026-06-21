#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "usage: sudo /home/rag/bin/rollback.sh /home/rag/releases/<sha>" >&2; exit 2; fi
target="$1"
[[ -d "$target" ]] || { echo "release not found: $target" >&2; exit 1; }
ln -sfn "$target" /home/rag/current
chown -h rag:rag /home/rag/current
cd /home/rag/current/construction-ai-rag-module
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml up -d --remove-orphans
curl -fsS http://127.0.0.1:8080/health/ready
