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

safe_state() {
  local api_id smoke_id scope_id context_scope_id realm_count audience_scope_count context_scope_count audience_mapper_count
  api_id="$(kc get clients -r techlab -q clientId=construction-rag-api --fields id --format csv --noquotes | awk 'NR==1{print}')"
  smoke_id="$(kc get clients -r techlab -q clientId=construction-rag-smoke-client --fields id --format csv --noquotes | awk 'NR==1{print}')"
  scope_id="$(kc get client-scopes -r techlab --fields id,name --format csv --noquotes | awk -F, '$2=="construction-rag-api-audience" && !found{print $1; found=1}')"
  context_scope_id="$(kc get client-scopes -r techlab --fields id,name --format csv --noquotes | awk -F, '$2=="construction-rag-context" && !found{print $1; found=1}')"
  [[ -n "$api_id" && -n "$smoke_id" && -n "$scope_id" && -n "$context_scope_id" ]] || {
    echo "required_object_lookup=FAIL" >&2
    return 1
  }
  realm_count="$(kc get realms --fields realm --format csv --noquotes | awk '$1=="techlab"{c++} END{print c+0}')"
  audience_scope_count="$(kc get client-scopes -r techlab --fields name --format csv --noquotes | awk '$1=="construction-rag-api-audience"{c++} END{print c+0}')"
  context_scope_count="$(kc get client-scopes -r techlab --fields name --format csv --noquotes | awk '$1=="construction-rag-context"{c++} END{print c+0}')"
  audience_mapper_count="$(kc get client-scopes/${scope_id}/protocol-mappers/models -r techlab --fields name --format csv --noquotes | awk '$1=="construction-rag-api-audience"{c++} END{print c+0}')"
  {
    echo "realm_count=${realm_count}"
    echo "api_client_count=$(kc get clients -r techlab -q clientId=construction-rag-api --fields id --format csv --noquotes | wc -l)"
    echo "smoke_client_count=$(kc get clients -r techlab -q clientId=construction-rag-smoke-client --fields id --format csv --noquotes | wc -l)"
    echo "audience_scope_count=${audience_scope_count}"
    echo "context_scope_count=${context_scope_count}"
    echo "api_roles=$( (kc get clients/${api_id}/roles -r techlab --fields name --format csv --noquotes | sort | grep -E '^(docs\\.admin|docs\\.view|policies\\.view|rag-user)$' || true) | tr '\\n' ',' )"
    echo "audience_mapper_count=${audience_mapper_count}"
    echo "context_mapper_names=$(kc get client-scopes/${context_scope_id}/protocol-mappers/models -r techlab --fields name --format csv --noquotes | sort | tr '\\n' ',' )"
    echo "smoke_mapper_names=$(kc get clients/${smoke_id}/protocol-mappers/models -r techlab --fields name --format csv --noquotes | sort | tr '\\n' ',' )"
    echo "smoke_default_scope_ids=$(kc get clients/${smoke_id}/default-client-scopes -r techlab --fields id --format csv --noquotes | sort | tr '\\n' ',' )"
    echo "realm_public_key_ids=$(curl -fsS https://modelauth.techlabeg.com/realms/techlab/protocol/openid-connect/certs | jq -r '.keys[] | select(.kty=="RSA") | .kid' | sort | tr '\\n' ',' )"
  } | sed 's/[[:space:]]*$//'
}

secret_hash() {
  local smoke_id
  smoke_id="$(kc get clients -r techlab -q clientId=construction-rag-smoke-client --fields id --format csv --noquotes | awk 'NR==1{print}')"
  kc get "clients/${smoke_id}/client-secret" -r techlab --fields value --format csv --noquotes | sha256sum | awk '{print $1}'
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
provision_script="${KEYCLOAK_PROVISION_SCRIPT:-/home/rag/bin/keycloak-provision.sh}"
[[ -x "$provision_script" || -f "$provision_script" ]] || { echo "provision_script_missing=FAIL" >&2; exit 1; }

initial_secret="$(secret_hash)"
safe_state > "$tmpdir/state0"
sha256sum "$tmpdir/state0" | awk '{print "state0_sha256="$1}'

for run in 1 2 3; do
  if ! bash "$provision_script" >/dev/null; then
    echo "idempotency_run_${run}=FAIL"
    exit 1
  fi
  current_secret="$(secret_hash)"
  if [[ "$current_secret" != "$initial_secret" ]]; then
    echo "client_secret_rotation=FAIL"
    exit 1
  fi
  safe_state > "$tmpdir/state${run}"
  sha256sum "$tmpdir/state${run}" | awk -v r="$run" '{print "run"r"_state_sha256="$1}'
  if [[ "$run" -gt 1 ]] && ! cmp -s "$tmpdir/state$((run - 1))" "$tmpdir/state${run}"; then
    echo "idempotency_run_${run}=FAIL"
    diff -u "$tmpdir/state$((run - 1))" "$tmpdir/state${run}" || true
    exit 1
  fi
  echo "idempotency_run_${run}=PASS"
done

final_state="$tmpdir/state3"
for expected in \
  "realm_count=1" \
  "api_client_count=1" \
  "smoke_client_count=1" \
  "audience_scope_count=1" \
  "context_scope_count=1" \
  "audience_mapper_count=1"; do
  if ! grep -Fxq "$expected" "$final_state"; then
    echo "expected_count_${expected}=FAIL"
    exit 1
  fi
done

echo "client_secret_rotation=PASS"
echo "realm_key_rotation=PASS"
echo "duplicate_objects=PASS"
