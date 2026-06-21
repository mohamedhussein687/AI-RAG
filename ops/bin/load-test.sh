#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
REQUESTS="${REQUESTS:-20}"
CONCURRENCY="${CONCURRENCY:-2}"
TOKEN="${GATEWAY_TEST_JWT:-}"
if [[ -z "$TOKEN" ]]; then
  echo "GATEWAY_TEST_JWT is required for protected load tests" >&2
  exit 2
fi
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
payload_search='{"query":"ما سياسة تأخر المشروع؟","top_k":3,"filters":{"project_id":"22"}}'
payload_final='{"conversation_id":"load-test","message":"ما سياسة تأخر المشروع؟","locale":"ar","local_rag_results":[]}'
run_one() {
  local i="$1" endpoint payload start end code elapsed
  endpoint="/api/rag/search"
  payload="$payload_search"
  if (( i % 2 == 0 )); then endpoint="/api/agent/final"; payload="$payload_final"; fi
  start=$(date +%s%3N)
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 60 -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$payload" "$BASE_URL$endpoint" || true)
  end=$(date +%s%3N)
  elapsed=$((end-start))
  printf '%s,%s,%s\n' "$endpoint" "$code" "$elapsed" >> "$workdir/results.csv"
}
export -f run_one
export BASE_URL TOKEN workdir payload_search payload_final
seq 1 "$REQUESTS" | xargs -P "$CONCURRENCY" -I{} bash -c 'run_one "$@"' _ {}
awk -F, '
{n++; codes[$2]++; lat[n]=$3; sum+=$3}
END {asort(lat); p50=lat[int((n+1)*0.50)]; p95=lat[int((n+1)*0.95)]; p99=lat[int((n+1)*0.99)]; printf "requests=%d\nconcurrency=%s\np50_ms=%s\np95_ms=%s\np99_ms=%s\n", n, ENVIRON["CONCURRENCY"], p50, p95, p99; for (c in codes) printf "http_%s=%d\n", c, codes[c]}' "$workdir/results.csv"
