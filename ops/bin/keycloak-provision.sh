#!/usr/bin/env bash
set -euo pipefail
set +x

if [[ ${EUID} -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

set -a
source /home/rag/.config/construction-rag/keycloak.env
set +a

cd /home/rag/auth
kc() {
  docker compose --env-file /home/rag/.config/construction-rag/keycloak.env -p construction-rag-auth -f compose.yml exec -T \
    -e KEYCLOAK_ADMIN_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" \
    keycloak bash -lc '
      /opt/keycloak/bin/kcadm.sh config credentials --server http://127.0.0.1:8080 --realm master --user "$KEYCLOAK_ADMIN_USERNAME" --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null
      /opt/keycloak/bin/kcadm.sh "$@"
    ' kcadm "$@"
}

if ! kc get realms/techlab >/dev/null 2>&1; then
  kc create realms -s realm=techlab -s enabled=true -s sslRequired=external -s registrationAllowed=false -s resetPasswordAllowed=true -s rememberMe=false -s bruteForceProtected=true -s accessTokenLifespan=900 -s ssoSessionIdleTimeout=1800 -s revokeRefreshToken=true >/dev/null
else
  kc update realms/techlab -s enabled=true -s sslRequired=external -s registrationAllowed=false -s rememberMe=false -s bruteForceProtected=true -s accessTokenLifespan=900 -s ssoSessionIdleTimeout=1800 -s revokeRefreshToken=true >/dev/null
fi

api_id="$(kc get clients -r techlab -q clientId=construction-rag-api --fields id --format csv --noquotes | head -n1 || true)"
if [[ -z "$api_id" ]]; then
  kc create clients -r techlab -s clientId=construction-rag-api -s name=construction-rag-api -s protocol=openid-connect -s publicClient=false -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false -s serviceAccountsEnabled=false -s enabled=true >/dev/null
  api_id="$(kc get clients -r techlab -q clientId=construction-rag-api --fields id --format csv --noquotes | head -n1)"
fi

for role in rag-user docs.admin docs.view policies.view; do
  kc get "clients/${api_id}/roles/${role}" -r techlab >/dev/null 2>&1 || kc create "clients/${api_id}/roles" -r techlab -s name="$role" >/dev/null
done

scope_id="$(kc get client-scopes -r techlab --fields id,name --format csv --noquotes | awk -F, '$2=="construction-rag-api-audience"{print $1; exit}')"
if [[ -z "$scope_id" ]]; then
  kc create client-scopes -r techlab -s name=construction-rag-api-audience -s protocol=openid-connect >/dev/null
  scope_id="$(kc get client-scopes -r techlab --fields id,name --format csv --noquotes | awk -F, '$2=="construction-rag-api-audience"{print $1; exit}')"
fi
if ! kc get "client-scopes/${scope_id}/protocol-mappers/models" -r techlab | grep -q '"name" *: *"construction-rag-api-audience"'; then
  kc create "client-scopes/${scope_id}/protocol-mappers/models" -r techlab \
    -s name=construction-rag-api-audience -s protocol=openid-connect -s protocolMapper=oidc-audience-mapper \
    -s 'config."included.client.audience"=construction-rag-api' -s 'config."access.token.claim"=true' >/dev/null
fi

context_scope_id="$(kc get client-scopes -r techlab --fields id,name --format csv --noquotes | awk -F, '$2=="construction-rag-context"{print $1; exit}')"
if [[ -z "$context_scope_id" ]]; then
  kc create client-scopes -r techlab -s name=construction-rag-context -s protocol=openid-connect >/dev/null
  context_scope_id="$(kc get client-scopes -r techlab --fields id,name --format csv --noquotes | awk -F, '$2=="construction-rag-context"{print $1; exit}')"
fi
for spec in "tenant_id:false" "project_ids:true" "roles:true" "permissions:true"; do
  claim="${spec%%:*}"
  multi="${spec##*:}"
  if ! kc get "client-scopes/${context_scope_id}/protocol-mappers/models" -r techlab | grep -q "\"name\" *: *\"${claim}\""; then
    kc create "client-scopes/${context_scope_id}/protocol-mappers/models" -r techlab \
      -s name="$claim" -s protocol=openid-connect -s protocolMapper=oidc-usermodel-attribute-mapper \
      -s "config.\"user.attribute\"=$claim" -s "config.\"claim.name\"=$claim" \
      -s 'config."jsonType.label"=String' -s 'config."access.token.claim"=true' -s "config.\"multivalued\"=$multi" >/dev/null
  fi
done

smoke_id="$(kc get clients -r techlab -q clientId=construction-rag-smoke-client --fields id --format csv --noquotes | head -n1 || true)"
if [[ -z "$smoke_id" ]]; then
  kc create clients -r techlab -s clientId=construction-rag-smoke-client -s name=construction-rag-smoke-client -s protocol=openid-connect -s publicClient=false -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false -s serviceAccountsEnabled=true -s enabled=true >/dev/null
  smoke_id="$(kc get clients -r techlab -q clientId=construction-rag-smoke-client --fields id --format csv --noquotes | head -n1)"
fi
kc update "clients/${smoke_id}/default-client-scopes/${scope_id}" -r techlab >/dev/null 2>&1 || true
kc delete "clients/${smoke_id}/default-client-scopes/${context_scope_id}" -r techlab >/dev/null 2>&1 || true

create_smoke_mapper() {
  local name="$1" value="$2"
  if ! kc get "clients/${smoke_id}/protocol-mappers/models" -r techlab | grep -q "\"name\" *: *\"${name}\""; then
    kc create "clients/${smoke_id}/protocol-mappers/models" -r techlab \
      -s name="$name" -s protocol=openid-connect -s protocolMapper=oidc-hardcoded-claim-mapper \
      -s "config.\"claim.name\"=$name" -s "config.\"claim.value\"=$value" \
      -s 'config."jsonType.label"=String' -s 'config."access.token.claim"=true' >/dev/null
  fi
}
create_smoke_mapper tenant_id smoke-tenant
create_smoke_mapper project_ids smoke-project
create_smoke_mapper roles rag-user
create_smoke_mapper permissions docs.admin,docs.view,policies.view

secret="$(kc get "clients/${smoke_id}/client-secret" -r techlab --fields value --format csv --noquotes)"
umask 077
cat > /home/rag/.config/construction-rag/keycloak-smoke.env.tmp <<EOF
KEYCLOAK_SMOKE_CLIENT_ID=construction-rag-smoke-client
KEYCLOAK_SMOKE_CLIENT_SECRET=${secret}
EOF
chown rag:rag /home/rag/.config/construction-rag/keycloak-smoke.env.tmp
chmod 600 /home/rag/.config/construction-rag/keycloak-smoke.env.tmp
mv /home/rag/.config/construction-rag/keycloak-smoke.env.tmp /home/rag/.config/construction-rag/keycloak-smoke.env
echo "keycloak provisioning complete"
