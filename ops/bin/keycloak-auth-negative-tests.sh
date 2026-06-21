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
      /opt/keycloak/bin/kcadm.sh config credentials --server http://127.0.0.1:8080 --realm master --user "$KEYCLOAK_ADMIN_USERNAME" --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null 2>&1
      /opt/keycloak/bin/kcadm.sh "$@"
    ' kcadm "$@"
}

first_client_id() {
  local realm="$1" client_id="$2" tmp
  tmp="$(mktemp)"
  kc get clients -r "$realm" -q clientId="$client_id" --fields id --format csv --noquotes > "$tmp"
  awk 'NR==1{print}' "$tmp"
  rm -f "$tmp"
}

first_scope_id() {
  local realm="$1" scope_name="$2" tmp
  tmp="$(mktemp)"
  kc get client-scopes -r "$realm" --fields id,name --format csv --noquotes > "$tmp"
  awk -F, -v n="$scope_name" '$2==n && !found{print $1; found=1}' "$tmp"
  rm -f "$tmp"
}

decode_payload() {
  python3 -c 'import base64,json,sys; p=sys.argv[1]; p += "=" * (-len(p) % 4); print(json.dumps(json.loads(base64.urlsafe_b64decode(p.encode())), separators=(",",":")))' "$1"
}

token_for_client() {
  local realm="$1" client_id="$2" secret="$3" output="$4"
  curl -fsS -o "$output" -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode grant_type=client_credentials \
    --data-urlencode client_id="$client_id" \
    --data-urlencode client_secret="$secret" \
    "https://modelauth.techlabeg.com/realms/${realm}/protocol/openid-connect/token"
}

call_status() {
  local endpoint="$1" body="$2" token_file="$3"
  curl -sS -o /tmp/codex-auth-negative-body -w '%{http_code}' \
    -H "Authorization: Bearer $(cat "$token_file")" \
    -H 'Content-Type: application/json' \
    -X POST "https://model.techlabeg.com${endpoint}" \
    --data "$body"
}

check_401_matrix() {
  local prefix="$1" token_file="$2" search_status chat_status decide_status
  search_status="$(call_status /api/rag/search '{"query":"السلامة"}' "$token_file")"
  chat_status="$(call_status /api/chat '{"message":"ما سياسة السلامة؟"}' "$token_file")"
  decide_status="$(call_status /api/agent/decide '{"message":"ما سياسة السلامة؟"}' "$token_file")"
  echo "${prefix}_search_status=${search_status}"
  echo "${prefix}_chat_status=${chat_status}"
  echo "${prefix}_decide_status=${decide_status}"
  [[ "$search_status" == 401 && "$chat_status" == 401 && "$decide_status" == 401 ]]
}

check_status_matrix() {
  local prefix="$1" expected="$2" token_file="$3" search_status chat_status decide_status
  search_status="$(call_status /api/rag/search '{"query":"السلامة"}' "$token_file")"
  chat_status="$(call_status /api/chat '{"message":"ما سياسة السلامة؟"}' "$token_file")"
  decide_status="$(call_status /api/agent/decide '{"message":"ما سياسة السلامة؟"}' "$token_file")"
  echo "${prefix}_search_status=${search_status}"
  echo "${prefix}_chat_status=${chat_status}"
  echo "${prefix}_decide_status=${decide_status}"
  [[ "$search_status" == "$expected" && "$chat_status" == "$expected" && "$decide_status" == "$expected" ]]
}

check_rejected_claim_matrix() {
  local prefix="$1" token_file="$2" search_status chat_status decide_status
  search_status="$(call_status /api/rag/search '{"query":"السلامة"}' "$token_file")"
  chat_status="$(call_status /api/chat '{"message":"ما سياسة السلامة؟"}' "$token_file")"
  decide_status="$(call_status /api/agent/decide '{"message":"ما سياسة السلامة؟"}' "$token_file")"
  echo "${prefix}_search_status=${search_status}"
  echo "${prefix}_chat_status=${chat_status}"
  echo "${prefix}_decide_status=${decide_status}"
  [[ "$search_status" =~ ^(401|403)$ && "$chat_status" =~ ^(401|403)$ && "$decide_status" =~ ^(401|403)$ ]]
}

create_claim_client() {
  local client="$1" tenant="$2" projects="$3" roles="$4" permissions="$5" client_id scope_id
  kc create clients -r techlab \
    -s clientId="$client" -s protocol=openid-connect -s publicClient=false \
    -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false \
    -s serviceAccountsEnabled=true -s enabled=true >/dev/null 2>&1
  client_id="$(first_client_id techlab "$client")"
  scope_id="$(first_scope_id techlab construction-rag-api-audience)"
  kc create "clients/${client_id}/default-client-scopes/${scope_id}" -r techlab >/dev/null 2>&1 || true
  add_claim_mapper "$client_id" tenant_id "$tenant"
  add_claim_mapper "$client_id" project_ids "$projects"
  add_claim_mapper "$client_id" roles "$roles"
  add_claim_mapper "$client_id" permissions "$permissions"
  echo "$client_id"
}

add_claim_mapper() {
  local client_id="$1" name="$2" value="$3"
  [[ -n "$value" ]] || return 0
  kc create "clients/${client_id}/protocol-mappers/models" -r techlab \
    -s name="$name" -s protocol=openid-connect -s protocolMapper=oidc-hardcoded-claim-mapper \
    -s "config.\"claim.name\"=$name" -s "config.\"claim.value\"=$value" \
    -s 'config."jsonType.label"=String' -s 'config."access.token.claim"=true' >/dev/null 2>&1
}

token_file_for_claim_client() {
  local client="$1" client_id="$2" output_prefix="$3" secret
  secret="$(kc get clients/${client_id}/client-secret -r techlab --fields value --format csv --noquotes)"
  token_for_client techlab "$client" "$secret" "${output_prefix}.json"
  jq -r .access_token "${output_prefix}.json" > "${output_prefix}.jwt"
}

tmpdir="$(mktemp -d)"
wrong_aud_client=""
wrong_aud_id=""
wrong_issuer_realm=""
claim_client_ids=()
trap 'set +e; if [[ -n "$wrong_aud_id" ]]; then kc delete clients/"$wrong_aud_id" -r techlab >/dev/null 2>&1; fi; for id in "${claim_client_ids[@]:-}"; do kc delete clients/"$id" -r techlab >/dev/null 2>&1; done; if [[ -n "$wrong_issuer_realm" ]]; then kc delete realms/"$wrong_issuer_realm" >/dev/null 2>&1; fi; rm -rf "$tmpdir" /tmp/codex-auth-negative-body' EXIT

wrong_aud_client="codex-wrong-aud-$(date -u +%s)"
kc create clients -r techlab \
  -s clientId="$wrong_aud_client" -s protocol=openid-connect -s publicClient=false \
  -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false \
  -s serviceAccountsEnabled=true -s enabled=true >/dev/null 2>&1
wrong_aud_id="$(first_client_id techlab "$wrong_aud_client")"
wrong_aud_secret="$(kc get clients/${wrong_aud_id}/client-secret -r techlab --fields value --format csv --noquotes)"
token_for_client techlab "$wrong_aud_client" "$wrong_aud_secret" "$tmpdir/wrong-aud-token.json"
jq -r .access_token "$tmpdir/wrong-aud-token.json" > "$tmpdir/wrong-aud.jwt"
wrong_aud_payload="$(decode_payload "$(cut -d. -f2 "$tmpdir/wrong-aud.jwt")")"
echo "wrong_audience_issuer=$(jq -r 'if .iss=="https://modelauth.techlabeg.com/realms/techlab" then "PASS" else "FAIL" end' <<< "$wrong_aud_payload")"
echo "wrong_audience_no_required_aud=$(jq -r 'if ((.aud|type)=="array" and (.aud|index("construction-rag-api")|not)) or ((.aud|type)=="string" and .aud!="construction-rag-api") then "PASS" else "FAIL" end' <<< "$wrong_aud_payload")"
echo "wrong_audience_expiration=$(jq -r 'if .exp > now then "PASS" else "FAIL" end' <<< "$wrong_aud_payload")"
check_401_matrix wrong_audience "$tmpdir/wrong-aud.jwt"

wrong_issuer_realm="codex-wrong-issuer-$(date -u +%s)"
wrong_issuer_client="codex-wrong-issuer-client"
kc create realms -s realm="$wrong_issuer_realm" -s enabled=true -s sslRequired=external >/dev/null 2>&1
kc create clients -r "$wrong_issuer_realm" \
  -s clientId="$wrong_issuer_client" -s protocol=openid-connect -s publicClient=false \
  -s standardFlowEnabled=false -s implicitFlowEnabled=false -s directAccessGrantsEnabled=false \
  -s serviceAccountsEnabled=true -s enabled=true >/dev/null 2>&1
wrong_issuer_id="$(first_client_id "$wrong_issuer_realm" "$wrong_issuer_client")"
wrong_issuer_secret="$(kc get clients/${wrong_issuer_id}/client-secret -r "$wrong_issuer_realm" --fields value --format csv --noquotes)"
token_for_client "$wrong_issuer_realm" "$wrong_issuer_client" "$wrong_issuer_secret" "$tmpdir/wrong-issuer-token.json"
jq -r .access_token "$tmpdir/wrong-issuer-token.json" > "$tmpdir/wrong-issuer.jwt"
wrong_issuer_payload="$(decode_payload "$(cut -d. -f2 "$tmpdir/wrong-issuer.jwt")")"
echo "wrong_issuer_differs=$(jq -r 'if .iss!="https://modelauth.techlabeg.com/realms/techlab" then "PASS" else "FAIL" end' <<< "$wrong_issuer_payload")"
echo "wrong_issuer_expiration=$(jq -r 'if .exp > now then "PASS" else "FAIL" end' <<< "$wrong_issuer_payload")"
check_401_matrix wrong_issuer "$tmpdir/wrong-issuer.jwt"

missing_tenant_client="codex-missing-tenant-$(date -u +%s)"
missing_tenant_id="$(create_claim_client "$missing_tenant_client" "" "smoke-project" "rag-user" "docs.view")"
claim_client_ids+=("$missing_tenant_id")
token_file_for_claim_client "$missing_tenant_client" "$missing_tenant_id" "$tmpdir/missing-tenant"
check_rejected_claim_matrix missing_tenant "$tmpdir/missing-tenant.jwt"

missing_project_client="codex-missing-project-$(date -u +%s)"
missing_project_id="$(create_claim_client "$missing_project_client" "smoke-tenant" "" "rag-user" "docs.view")"
claim_client_ids+=("$missing_project_id")
token_file_for_claim_client "$missing_project_client" "$missing_project_id" "$tmpdir/missing-project"
check_rejected_claim_matrix missing_project "$tmpdir/missing-project.jwt"

missing_permission_client="codex-missing-permission-$(date -u +%s)"
missing_permission_id="$(create_claim_client "$missing_permission_client" "smoke-tenant" "smoke-project" "rag-user" "")"
claim_client_ids+=("$missing_permission_id")
token_file_for_claim_client "$missing_permission_client" "$missing_permission_id" "$tmpdir/missing-permission"
check_rejected_claim_matrix missing_permission "$tmpdir/missing-permission.jwt"

echo "negative_auth_tests=PASS"
