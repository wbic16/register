#!/bin/bash
# register-service — one-run install on awsbox. Run as wbic16:
#
#     bash ~/register-service-deploy/install-on-box.sh
#
# The staging dir (this script's own directory) must contain:
#   regsvc/                      the service package
#   requirements.txt             pinned Python deps (ldap3, webauthn)
#   register-service.service     systemd unit
#   register-service.env         environment file template
#   register.phext.io.https.conf v2 vhost (adds the /api/ proxy)
#   ldap-ca.crt                  Bickford House CA (public cert)
#   index.html                   v2 register page
#   register-numbers.json        open register numbers (Done validation)
#
# Steps: create the regsvc user + dirs, install the app + venv, create
# the HMAC secret (once), install the CA cert, enable the systemd
# service, run the LDAP fail-closed selftest, swap the page files and
# the nginx vhost, reload, and verify page + API over HTTPS.
# Safe to re-run: every step is idempotent; the secret is never rotated
# by this script. NOTE: verify steps download to temp files and grep
# the files — never pipe curl into grep -q (SIGPIPE + pipefail turns a
# successful check into a fatal error; learned 2026-11-15).
set -euo pipefail

DOMAIN=register.phext.io
ROOT=/sites/web/register.phext.io
STAGE="$(cd "$(dirname "$0")" && pwd)"
APP=/opt/register-service
CONFDIR=/etc/register-service
DATA=/var/lib/register-service

echo "== staging check =="
for f in requirements.txt register-service.service register-service.env \
         register.phext.io.https.conf ldap-ca.crt index.html \
         register-numbers.json; do
  [ -f "$STAGE/$f" ] || { echo "MISSING staged file: $f"; exit 1; }
done
[ -d "$STAGE/regsvc" ] || { echo "MISSING staged dir: regsvc/"; exit 1; }
echo "staging OK"

echo "== user + directories =="
if ! id regsvc >/dev/null 2>&1; then
  sudo useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin regsvc
fi
sudo mkdir -p "$APP" "$CONFDIR" "$DATA"
sudo chown regsvc:regsvc "$DATA"
sudo chmod 750 "$DATA"

echo "== install app + CA + env =="
sudo rm -rf "$APP/regsvc"
sudo cp -r "$STAGE/regsvc" "$APP/regsvc"
sudo cp "$STAGE/requirements.txt" "$APP/requirements.txt"
sudo cp "$STAGE/ldap-ca.crt" "$CONFDIR/ldap-ca.crt"
sudo chmod 644 "$CONFDIR/ldap-ca.crt"
if [ ! -f "$CONFDIR/env" ]; then
  sudo cp "$STAGE/register-service.env" "$CONFDIR/env"
fi

echo "== HMAC secret (created once, never rotated here) =="
if [ ! -f "$CONFDIR/secret" ]; then
  openssl rand -hex 32 | sudo tee "$CONFDIR/secret" >/dev/null
  sudo chown regsvc:regsvc "$CONFDIR/secret"
  sudo chmod 600 "$CONFDIR/secret"
  echo "secret created"
else
  echo "secret already exists — kept"
fi

echo "== drain token (generated once, appended to env) =="
if ! grep -q '^REGSVC_DRAIN_TOKEN=' "$CONFDIR/env"; then
  echo "REGSVC_DRAIN_TOKEN=$(openssl rand -hex 24)" | sudo tee -a "$CONFDIR/env" >/dev/null
  echo "drain token generated (in $CONFDIR/env — Emise's ticks read the two queue logs with it)"
else
  echo "drain token already present — kept"
fi

echo "== python venv + deps =="
if [ ! -x "$APP/venv/bin/python" ]; then
  if ! sudo python3 -m venv "$APP/venv" 2>/dev/null || \
     [ ! -x "$APP/venv/bin/pip" ]; then
    echo "venv incomplete — installing python3-venv and retrying"
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv
    sudo rm -rf "$APP/venv"
    sudo python3 -m venv "$APP/venv"
  fi
fi
sudo "$APP/venv/bin/pip" install --quiet -r "$APP/requirements.txt"
sudo chown -R regsvc:regsvc "$APP"
echo "deps installed"

echo "== systemd service =="
sudo cp "$STAGE/register-service.service" /etc/systemd/system/register-service.service
sudo systemctl daemon-reload
sudo systemctl enable --now register-service
sleep 1
sudo systemctl is-active register-service

echo "== LDAP selftest (probe bind must be refused) =="
sudo -u regsvc env PYTHONPATH="$APP" $(grep -v '^#' "$CONFDIR/env" | grep -v '^$') \
  "$APP/venv/bin/python" -m regsvc.server --selftest

echo "== local API health =="
curl -fsS "http://127.0.0.1:8791/api/health" -o /tmp/regsvc-verify-health.json
grep -q '"ok": true' /tmp/regsvc-verify-health.json
echo "API OK"

echo "== page files (v2 page + numbers) =="
cp "$STAGE/index.html" "$ROOT/index.html"
cp "$STAGE/register-numbers.json" "$ROOT/register-numbers.json"
chmod 644 "$ROOT/index.html" "$ROOT/register-numbers.json"

echo "== nginx vhost v2 (/api/ proxy) =="
sudo cp "$STAGE/register.phext.io.https.conf" "/etc/nginx/sites-available/$DOMAIN"
sudo nginx -t
sudo systemctl reload nginx

echo "== verify over HTTPS =="
curl -fsS "https://$DOMAIN/" -o /tmp/regsvc-verify-page.html
grep -q "open items" /tmp/regsvc-verify-page.html
curl -fsS "https://$DOMAIN/api/session" -o /tmp/regsvc-verify-session.json
grep -q '"user": null' /tmp/regsvc-verify-session.json
echo "HTTPS OK — https://$DOMAIN/ serves the v2 page and the API answers"
echo "Next: log in with your LDAP password, then 'Add a passkey'."
