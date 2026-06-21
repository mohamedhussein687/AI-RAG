#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi
if [[ $# -ne 1 ]]; then
  echo "usage: $0 <backup-directory>" >&2
  exit 2
fi
backup="$1"
dump="$backup/keycloak-postgres.sql"
if [[ ! -r "$dump" ]]; then
  echo "backup dump not found" >&2
  exit 3
fi

tmp="/home/rag/auth-restore-test-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$tmp/data"
cat > "$tmp/compose.yml" <<'YAML'
name: construction-rag-auth-restore-test
services:
  postgres:
    image: postgres:16.6-bookworm@sha256:557fea37a744d5f4c8faab304b0a90858b53ab119735a88c131fd19dab802f36
    environment:
      POSTGRES_DB: keycloak
      POSTGRES_USER: keycloak
      POSTGRES_PASSWORD: restore-test-password
    volumes:
      - ./data:/var/lib/postgresql/data
    networks: [restore]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U keycloak -d keycloak"]
      interval: 5s
      timeout: 3s
      retries: 20
networks:
  restore:
    internal: true
YAML
cd "$tmp"
docker compose -f compose.yml up -d
trap 'cd "$tmp" && docker compose -f compose.yml down -v >/dev/null 2>&1 || true' EXIT
for i in $(seq 1 40); do
  if docker compose -f compose.yml exec -T postgres pg_isready -U keycloak -d keycloak >/dev/null 2>&1; then break; fi
  sleep 2
done
docker compose -f compose.yml exec -T postgres psql -U keycloak -d keycloak < "$dump" >/dev/null
docker compose -f compose.yml exec -T postgres psql -U keycloak -d keycloak -Atc "select count(*) from realm where name='techlab'; select count(*) from client where client_id in ('construction-rag-api','construction-rag-smoke-client');" > "$backup/restore-test-counts.txt"
echo "isolated restore test complete: $backup/restore-test-counts.txt"
