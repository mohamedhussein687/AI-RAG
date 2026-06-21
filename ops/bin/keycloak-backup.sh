#!/usr/bin/env bash
set -euo pipefail
set +x

if [[ ${EUID} -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="/home/rag/backups/keycloak/${stamp}"
umask 077
mkdir -p "$dest"
set -a
source /home/rag/.config/construction-rag/keycloak.env
set +a

cd /home/rag/auth
docker compose --env-file /home/rag/.config/construction-rag/keycloak.env -p construction-rag-auth -f compose.yml exec -T keycloak-postgres \
  pg_dump -U "$KEYCLOAK_DB_USER" --no-owner --no-acl "$KEYCLOAK_DB_NAME" > "$dest/keycloak-postgres.sql"
docker compose --env-file /home/rag/.config/construction-rag/keycloak.env -p construction-rag-auth -f compose.yml images > "$dest/images.txt"
sha256sum /home/rag/auth/compose.yml /home/rag/auth/Containerfile /etc/nginx/sites-available/modelauth.techlabeg.com > "$dest/config-sha256.txt"
cp -a /etc/nginx/sites-available/modelauth.techlabeg.com "$dest/nginx-modelauth.conf"
openssl x509 -in /etc/letsencrypt/live/modelauth.techlabeg.com/fullchain.pem -noout -subject -issuer -dates -ext subjectAltName > "$dest/certificate-metadata.txt" 2>/dev/null || true
readlink -f /home/rag/current > "$dest/rag-current-release.txt"
chmod -R go-rwx "$dest"
echo "$dest"
