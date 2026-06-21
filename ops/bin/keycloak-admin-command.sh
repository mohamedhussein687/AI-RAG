#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <kcadm arguments...>" >&2
  exit 2
fi

set -a
source /home/rag/.config/construction-rag/keycloak.env
set +a

cd /home/rag/auth
docker compose --env-file /home/rag/.config/construction-rag/keycloak.env -p construction-rag-auth -f compose.yml exec -T \
  -e KEYCLOAK_ADMIN_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" \
  keycloak bash -lc '
    /opt/keycloak/bin/kcadm.sh config credentials \
      --server http://127.0.0.1:8080 \
      --realm master \
      --user "$KEYCLOAK_ADMIN_USERNAME" \
      --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null
    /opt/keycloak/bin/kcadm.sh "$@"
  ' kcadm "$@"
