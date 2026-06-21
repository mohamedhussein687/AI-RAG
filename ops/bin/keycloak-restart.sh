#!/usr/bin/env bash
set -euo pipefail
cd /home/rag/auth
docker compose --env-file /home/rag/.config/construction-rag/keycloak.env -p construction-rag-auth -f compose.yml up -d
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8180/realms/master/.well-known/openid-configuration >/dev/null; then
    echo "keycloak ready"
    exit 0
  fi
  sleep 2
done
echo "keycloak did not become ready" >&2
exit 1
