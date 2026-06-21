#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: sudo /home/rag/bin/rollback.sh /home/rag/releases/<sha>" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
target="$(readlink -f "$1")"
[[ "$target" == /home/rag/releases/* ]] || { echo "target must be under /home/rag/releases" >&2; exit 1; }
[[ -d "$target" ]] || { echo "release not found: $target" >&2; exit 1; }

target_sha="$(basename "$target")"
[[ "$target_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "target release basename is not a Git SHA: $target_sha" >&2; exit 1; }
[[ -f "$target/construction-ai-rag-module/docker-compose.prod.yml" ]] || { echo "target compose file missing" >&2; exit 1; }
[[ -f "$target/construction-gateway/pom.xml" ]] || { echo "target gateway source missing" >&2; exit 1; }

env_file="/home/rag/.config/construction-rag/production.env"
previous="$(readlink -f /home/rag/current)"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
env_backup="${env_file}.rollback-${timestamp}"

require_image() {
  local image="$1"
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "required immutable image missing: $image" >&2
    return 1
  fi
}

set_release_sha() {
  local sha="$1" tmp
  tmp="$(mktemp "${env_file}.tmp.XXXXXX")"
  awk -v sha="$sha" '
    BEGIN { written=0 }
    /^RELEASE_SHA=/ {
      if (!written) {
        print "RELEASE_SHA=" sha
        written=1
      }
      next
    }
    { print }
    END {
      if (!written) print "RELEASE_SHA=" sha
    }
  ' "$env_file" > "$tmp"
  chown --reference="$env_file" "$tmp"
  chmod --reference="$env_file" "$tmp"
  mv "$tmp" "$env_file"
}

wait_ready() {
  local timeout_seconds="${RAG_READY_TIMEOUT_SECONDS:-180}" elapsed
  for elapsed in $(seq 1 "$timeout_seconds"); do
    if curl -fsS http://127.0.0.1:8080/health/ready 2>/dev/null | grep -q '"status":"ok"'; then
      return 0
    fi
    sleep 1
  done
  return 1
}

activate_release() {
  local release_path="$1" sha="$2"
  ln -sfn "$release_path" /home/rag/current
  chown -h rag:rag /home/rag/current
  set_release_sha "$sha"
  cd /home/rag/current/construction-ai-rag-module
  docker compose --env-file "$env_file" -f docker-compose.prod.yml up -d --no-deps --force-recreate ai-module-api
  if ! docker compose --env-file "$env_file" -f docker-compose.prod.yml ps ai-module-api | grep -q healthy; then
    for _ in $(seq 1 120); do
      docker compose --env-file "$env_file" -f docker-compose.prod.yml ps ai-module-api | grep -q healthy && break
      sleep 1
    done
  fi
  docker compose --env-file "$env_file" -f docker-compose.prod.yml up -d --no-deps --force-recreate spring-gateway
}

restore_previous() {
  echo "rollback activation failed; restoring previous release $previous" >&2
  cp -a "$env_backup" "$env_file"
  ln -sfn "$previous" /home/rag/current
  chown -h rag:rag /home/rag/current
  cd /home/rag/current/construction-ai-rag-module
  docker compose --env-file "$env_file" -f docker-compose.prod.yml up -d --no-deps --force-recreate ai-module-api spring-gateway >/dev/null 2>&1 || true
}

cp -a "$env_file" "$env_backup"
chmod go-rwx "$env_backup"

require_image "construction-rag/ai-module:${target_sha}"
require_image "construction-rag/spring-gateway:${target_sha}"

if ! activate_release "$target" "$target_sha"; then
  restore_previous
  exit 1
fi

if ! wait_ready; then
  echo "rollback target did not become ready" >&2
  restore_previous
  exit 1
fi

active="$(readlink -f /home/rag/current)"
gateway_image="$(docker inspect construction-rag-spring-gateway-1 --format '{{.Config.Image}}' 2>/dev/null || true)"
ai_image="$(docker inspect construction-rag-ai-module-api-1 --format '{{.Config.Image}}' 2>/dev/null || true)"
echo "rollback ready: $active"
echo "release_sha=$target_sha"
echo "gateway_image=$gateway_image"
echo "ai_image=$ai_image"
