"""Register service entrypoint.

Config via environment:
  REGSVC_DATA_DIR     data dir (default /var/lib/register-service)
  REGSVC_SECRET_FILE  HMAC secret file (default $DATA_DIR/secret);
                      must exist and hold >= 32 bytes — install creates it
  REGSVC_LDAP_HOST    default aletheia-core.pizzly-halfmoon.ts.net
                      (the DNS name, so LDAPS hostname verification
                      matches the server certificate)
  REGSVC_LDAP_CA      house CA cert (default /etc/register-service/ldap-ca.crt)
  REGSVC_RP_ID        default register.phext.io
  REGSVC_ORIGIN       default https://register.phext.io
  REGSVC_NUMBERS_FILE open register numbers JSON
                      (default /sites/web/register.phext.io/register-numbers.json)
  REGSVC_PORT         default 8791 (binds 127.0.0.1 only; nginx proxies)
  REGSVC_DRAIN_TOKEN  optional; when set, header X-Drain-Token with
                      this value may read (only) the two queue logs —
                      Emise's ticks drain headlessly with it
  REGSVC_DRAIN_USER   the login whose scope the drain token reads
                      (per-user drain); without it the drain token
                      authorizes nothing
  REGSVC_NUMBERS_OWNER  owner uid for register numbers in a legacy
                      flat-list numbers file (the scoped object form
                      names each number's owner in the file itself)

Modes:
  (default)   serve
  --selftest  attempt an LDAP bind with a nonexistent probe uid and a
              deliberately wrong password; exit 0 iff the directory
              answers "invalid credentials" (path works, fails closed).
"""

import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .app import RegisterApp
from .ldap_auth import LdapAuthenticator, LdapUnavailable
from .store import CredentialStore, JsonlLog, SessionStore
from .webauthn_auth import WebAuthnCeremonies


def build_app(env=None):
    env = env or os.environ
    data_dir = Path(env.get("REGSVC_DATA_DIR", "/var/lib/register-service"))
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file = Path(env.get("REGSVC_SECRET_FILE",
                               str(data_dir / "secret")))
    secret = secret_file.read_bytes().strip()
    if len(secret) < 32:
        raise SystemExit(f"secret in {secret_file} too short or missing")
    ldap_auth = LdapAuthenticator(
        host=env.get("REGSVC_LDAP_HOST",
                     "aletheia-core.pizzly-halfmoon.ts.net"),
        ca_cert_file=env.get("REGSVC_LDAP_CA",
                             "/etc/register-service/ldap-ca.crt"),
    )
    ceremonies = WebAuthnCeremonies(
        rp_id=env.get("REGSVC_RP_ID", "register.phext.io"),
        origin=env.get("REGSVC_ORIGIN", "https://register.phext.io"),
    )
    return RegisterApp(
        entries_log=JsonlLog(data_dir / "pending-entries.jsonl"),
        resolutions_log=JsonlLog(data_dir / "resolutions.jsonl"),
        credentials=CredentialStore(data_dir / "credentials.json"),
        sessions=SessionStore(data_dir / "sessions.json"),
        ldap_auth=ldap_auth,
        ceremonies=ceremonies,
        secret=secret,
        drain_token=env.get("REGSVC_DRAIN_TOKEN") or None,
        drain_user=env.get("REGSVC_DRAIN_USER") or None,
        numbers_owner=env.get("REGSVC_NUMBERS_OWNER") or None,
        numbers_file=env.get(
            "REGSVC_NUMBERS_FILE",
            "/sites/web/register.phext.io/register-numbers.json"),
    )


def selftest(env=None):
    env = env or os.environ
    auth = LdapAuthenticator(
        host=env.get("REGSVC_LDAP_HOST",
                     "aletheia-core.pizzly-halfmoon.ts.net"),
        ca_cert_file=env.get("REGSVC_LDAP_CA",
                             "/etc/register-service/ldap-ca.crt"),
    )
    try:
        result = auth.authenticate("register-service-probe",
                                   "probe-definitely-wrong")
    except LdapUnavailable as exc:
        print(f"selftest FAIL: directory unavailable: {exc}")
        return 1
    if result is None:
        print("selftest OK: directory reachable, probe bind refused "
              "(invalid credentials), fail-closed confirmed")
        return 0
    print("selftest FAIL: probe bind unexpectedly succeeded")
    return 1


class Handler(BaseHTTPRequestHandler):
    app = None  # set in main
    protocol_version = "HTTP/1.1"

    def _dispatch(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        headers = {k: v for k, v in self.headers.items()}
        status, resp_headers, resp_body = self.app.handle(
            method, self.path, headers, body)
        self.send_response(status)
        for k, v in resp_headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(resp_body)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def log_message(self, fmt, *args):  # keep journald noise low
        sys.stderr.write("%s - %s\n" % (self.address_string(),
                                        fmt % args))


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    app = build_app()
    Handler.app = app
    port = int(os.environ.get("REGSVC_PORT", "8791"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"register-service listening on 127.0.0.1:{port}",
          file=sys.stderr)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
