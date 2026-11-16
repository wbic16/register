#!/bin/bash
# One-run update: per-user scoping for the register service.
#
# This is the SINGLE staged update for everything pending:
#   - the dialog+cancel service code (PRs #7/#8 — already the lineage
#     of the staged regsvc files, never yet installed on the box), and
#   - per-user scoping (2026-11-16): all register data scoped by the
#     caller's login; existing data migrated into wbic16's scope;
#     the drain token reads only wbic16's scope; register numbers
#     carry their owner (scoped register-numbers.json rides along).
#
# Run on awsbox:  sudo bash ~/register-service-deploy/update-on-box.sh
set -euo pipefail
SRC="$HOME/register-service-deploy"
DATA=/var/lib/register-service
ENV=/etc/register-service/env
OWNER=wbic16

echo "== staged files =="
for f in app.py store.py server.py migrate_scope.py index.html \
         register-numbers.json; do
  if [ ! -f "$SRC/$f" ]; then echo "MISSING staged file: $f"; exit 1; fi
done
sha256sum "$SRC/app.py" "$SRC/store.py" "$SRC/server.py" \
          "$SRC/migrate_scope.py" "$SRC/index.html" \
          "$SRC/register-numbers.json"

echo "== stop service (restarts automatically if anything fails) =="
systemctl stop register-service
trap 'systemctl start register-service || true' ERR

echo "== env: scope config (key names only; values never printed) =="
grep -q '^REGSVC_DRAIN_USER=' "$ENV" \
  || echo "REGSVC_DRAIN_USER=$OWNER" >> "$ENV"
grep -q '^REGSVC_NUMBERS_OWNER=' "$ENV" \
  || echo "REGSVC_NUMBERS_OWNER=$OWNER" >> "$ENV"
grep -o '^REGSVC_[A-Z_]*' "$ENV" | sort

echo "== migrate existing data into $OWNER's scope =="
runuser -u regsvc -- python3 "$SRC/migrate_scope.py" \
  --data-dir "$DATA" --uid "$OWNER"

echo "== install service code =="
install -m 644 "$SRC/app.py" /opt/register-service/regsvc/app.py
install -m 644 "$SRC/store.py" /opt/register-service/regsvc/store.py
install -m 644 "$SRC/server.py" /opt/register-service/regsvc/server.py
install -m 644 "$SRC/migrate_scope.py" \
  /opt/register-service/regsvc/migrate_scope.py

echo "== install page + scoped numbers =="
install -m 644 "$SRC/index.html" /sites/web/register.phext.io/index.html
install -m 644 "$SRC/register-numbers.json" \
  /sites/web/register.phext.io/register-numbers.json

echo "== start + verify =="
systemctl start register-service
sleep 1
systemctl is-active register-service
curl -s http://127.0.0.1:8791/api/health
echo
curl -s https://register.phext.io/ -o /tmp/reg-verify.html
echo "live page vs staged page:"
sha256sum /tmp/reg-verify.html "$SRC/index.html"
grep -c "Cancel entry" /tmp/reg-verify.html || true

echo "== scoped drain smoke (token read from env, never printed) =="
TOKEN=$(grep '^REGSVC_DRAIN_TOKEN=' "$ENV" | cut -d= -f2-)
for log in entries/pending resolutions; do
  curl -s -H "X-Drain-Token: $TOKEN" \
    "http://127.0.0.1:8791/api/$log" -o /tmp/reg-drain.json
  python3 - "$log" <<'PY'
import json, sys
body = json.load(open("/tmp/reg-drain.json"))
atoms = body["atoms"]
bad = [a.get("seq") for a in atoms if a.get("user") != "wbic16"]
assert not bad, f"{sys.argv[1]}: atoms outside wbic16 scope: {bad}"
print(f"{sys.argv[1]}: {len(atoms)} atoms, all scoped to wbic16")
PY
done

trap - ERR
echo "UPDATE OK"
