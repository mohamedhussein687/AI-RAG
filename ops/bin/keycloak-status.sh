#!/usr/bin/env bash
set -euo pipefail
cd /home/rag/auth
docker compose --env-file /home/rag/.config/construction-rag/keycloak.env -p construction-rag-auth -f compose.yml ps
curl -fsS http://127.0.0.1:8180/realms/master/.well-known/openid-configuration >/dev/null && echo "master discovery: ok"
curl -fsS https://modelauth.techlabeg.com/realms/techlab/.well-known/openid-configuration >/dev/null && echo "techlab discovery: ok"
