#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi
if [[ $# -ne 1 ]]; then
  echo "usage: $0 <IP_ADDRESS>" >&2
  exit 2
fi

ip="$1"
python3 - "$ip" <<'PY'
import ipaddress, sys
ipaddress.ip_address(sys.argv[1])
PY

snippet=/etc/nginx/snippets/modelauth-admin-allowlist.conf
backup="/home/rag/backups/modelauth-admin-allowlist-$(date -u +%Y%m%dT%H%M%SZ).conf"
install -d -m 700 /home/rag/backups
if [[ -f "$snippet" ]]; then
  cp -a "$snippet" "$backup"
fi
tmp="$(mktemp "${snippet}.XXXX")"
cat > "$tmp" <<EOF
allow 127.0.0.1;
allow ::1;
allow ${ip};
deny all;
EOF
chmod 0644 "$tmp"
mv "$tmp" "$snippet"
nginx -t
systemctl reload nginx
echo "admin allowlist updated"
