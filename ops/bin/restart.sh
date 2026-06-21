#!/usr/bin/env bash
set -euo pipefail
cd /home/rag/current/construction-ai-rag-module
docker compose --env-file /home/rag/.config/construction-rag/production.env -f docker-compose.prod.yml up -d --remove-orphans
