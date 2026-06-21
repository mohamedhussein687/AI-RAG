#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
domain=""; email=""
while [[ $# -gt 0 ]]; do case "$1" in --domain) domain="${2:-}"; shift 2;; --email) email="${2:-}"; shift 2;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done
[[ -n "$domain" && -n "$email" ]] || { echo "usage: sudo /home/rag/bin/configure-domain.sh --domain DOMAIN --email EMAIL" >&2; exit 2; }
[[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$ ]] || { echo "invalid domain" >&2; exit 2; }
[[ "$email" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || { echo "invalid email" >&2; exit 2; }
server_ips="$(curl -fsS --max-time 5 https://api64.ipify.org || true)"
dns_ips="$(getent ahosts "$domain" | awk '{print $1}' | sort -u | tr '
' ' ')"
[[ -n "$server_ips" && " $dns_ips " == *" $server_ips "* ]] || { echo "DNS for $domain does not point to this server ($server_ips); got: $dns_ips" >&2; exit 1; }
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx
site="/etc/nginx/sites-available/$domain"
enabled="/etc/nginx/sites-enabled/$domain"
backup="/etc/nginx/backup-$domain-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup"
[[ -e "$site" ]] && cp -a "$site" "$backup/"
cat > "$site" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $domain;
    client_max_body_size 20m;
    proxy_read_timeout 120s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 120s;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Request-ID \$request_id;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX
ln -sfn "$site" "$enabled"
nginx -t
if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow OpenSSH; ufw allow 80/tcp; ufw allow 443/tcp; fi
certbot --nginx -d "$domain" --non-interactive --agree-tos -m "$email" --redirect
certbot renew --dry-run
nginx -t && systemctl reload nginx
curl -fsS "http://$domain/health/live" >/dev/null || true
curl -fsS "https://$domain/health/live" >/dev/null
