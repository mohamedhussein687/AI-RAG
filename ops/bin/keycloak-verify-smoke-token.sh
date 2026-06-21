#!/usr/bin/env bash
set -euo pipefail
set +x

token_file="${1:-}"
if [[ -z "$token_file" || ! -r "$token_file" ]]; then
  echo "usage: $0 <protected-token-file>" >&2
  exit 2
fi

python3 - "$token_file" <<'PY'
import base64, json, sys, time, urllib.request

token = open(sys.argv[1], "r", encoding="utf-8").read().strip()
parts = token.split(".")
if len(parts) != 3:
    print("INVALID malformed")
    raise SystemExit(1)

def b64url(data):
    data += "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data.encode())

header = json.loads(b64url(parts[0]))
payload = json.loads(b64url(parts[1]))
issuer = "https://modelauth.techlabeg.com/realms/techlab"
jwks_uri = issuer + "/protocol/openid-connect/certs"
jwks = json.load(urllib.request.urlopen(jwks_uri, timeout=10))
kid_ok = any(k.get("kid") == header.get("kid") and k.get("kty") in {"RSA", "EC", "OKP"} and "d" not in k for k in jwks.get("keys", []))
aud = payload.get("aud", [])
if isinstance(aud, str):
    aud = [aud]
checks = {
    "issuer": payload.get("iss") == issuer,
    "audience": "construction-rag-api" in aud,
    "expiration": isinstance(payload.get("exp"), int) and payload["exp"] > int(time.time()),
    "subject": bool(payload.get("sub")),
    "tenant_id": bool(payload.get("tenant_id")),
    "project_ids": bool(payload.get("project_ids")),
    "roles": bool(payload.get("roles")),
    "permissions": bool(payload.get("permissions")),
    "jwks_kid": kid_ok,
}
valid = all(checks.values())
print("VALID" if valid else "INVALID")
for key, ok in checks.items():
    print(f"{key}={'PASS' if ok else 'FAIL'}")
raise SystemExit(0 if valid else 1)
PY
