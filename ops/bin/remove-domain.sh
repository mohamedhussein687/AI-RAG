#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
[[ $# -eq 2 && "$1" == "--domain" ]] || { echo "usage: sudo /home/rag/bin/remove-domain.sh --domain DOMAIN" >&2; exit 2; }
domain="$2"
rm -f "/etc/nginx/sites-enabled/$domain"
nginx -t && systemctl reload nginx
