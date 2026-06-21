#!/usr/bin/env bash
set -euo pipefail
set +x

env_file=/home/rag/.config/construction-rag/keycloak-smoke.env
if [[ ! -r "$env_file" ]]; then
  echo "smoke client env is missing" >&2
  exit 1
fi
set -a
source "$env_file"
set +a

curl -fsS \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode "client_id=${KEYCLOAK_SMOKE_CLIENT_ID}" \
  --data-urlencode "client_secret=${KEYCLOAK_SMOKE_CLIENT_SECRET}" \
  'https://modelauth.techlabeg.com/realms/techlab/protocol/openid-connect/token' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
