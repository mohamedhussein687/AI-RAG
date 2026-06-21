#!/usr/bin/env bash
set -euo pipefail
cd /home/rag/current/construction-ai-rag-module
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml ps
curl -fsS http://127.0.0.1:8080/health/ready || true
nvidia-smi || true
