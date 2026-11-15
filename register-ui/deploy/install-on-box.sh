#!/bin/bash
# register.phext.io — one-time install on awsbox. Run as wbic16:
#
#     bash ~/register-deploy/install-on-box.sh
#
# Everything that needs root is in here (sudo will prompt for the
# password). Steps:
#   1. Install the HTTP bootstrap vhost, reload nginx.
#   2. If register.phext.io resolves: verify the page over HTTP,
#      run a certbot --dry-run against staging, then issue the
#      production certificate exactly once (skipped if one exists).
#   3. Swap in the HTTPS vhost pair, reload, verify over HTTPS.
# If DNS has not propagated yet, step 1 still lands and the rest is
# skipped with a message — just re-run this script once DNS is live.
# Safe to re-run.
set -euo pipefail

DOMAIN=register.phext.io
ROOT=/sites/web/register.phext.io
STAGE="$(cd "$(dirname "$0")" && pwd)"

echo "== DNS check =="
IP="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)"
if [ -z "${IP:-}" ]; then
  echo "WARNING: $DOMAIN does not resolve from this box yet."
fi

echo "== install HTTP bootstrap vhost =="
sudo cp "$STAGE/register.phext.io.http.conf" "/etc/nginx/sites-available/$DOMAIN"
sudo ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
sudo nginx -t
sudo systemctl reload nginx
echo "HTTP vhost installed."

if [ -z "${IP:-}" ]; then
  echo "Skipping certificate + HTTPS steps (no DNS yet)."
  echo "Re-run this script once $DOMAIN resolves to this box."
  exit 0
fi

echo "== verify page over HTTP =="
curl -fsS "http://$DOMAIN/" | grep -q "open items"
echo "HTTP OK"

if [ -e "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
  echo "== certificate already exists — skipping issuance =="
else
  echo "== certbot dry run (staging, does not burn production budget) =="
  sudo certbot certonly --webroot -w "$ROOT" -d "$DOMAIN" \
    --dry-run --non-interactive --agree-tos
  echo "== certbot production issuance (once) =="
  sudo certbot certonly --webroot -w "$ROOT" -d "$DOMAIN" \
    --non-interactive --agree-tos
fi

echo "== install HTTPS vhost pair =="
sudo cp "$STAGE/register.phext.io.https.conf" "/etc/nginx/sites-available/$DOMAIN"
sudo nginx -t
sudo systemctl reload nginx

echo "== verify page over HTTPS =="
curl -fsS "https://$DOMAIN/" | grep -q "open items"
echo "HTTPS OK — https://$DOMAIN is live"
