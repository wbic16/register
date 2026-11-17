"""HTTP application for the register service.

Transport-independent core: ``RegisterApp.handle(method, path, headers,
body) -> (status, headers, body)``; server.py adapts it to
http.server. All state-changing endpoints require a session; all auth
failures fail closed. All register data is scoped by the caller's
login: queue reads return only the caller's atoms (the drain token
reads only its configured user's), and an item can be closed only by
the login that owns its register number. The service NEVER writes the
register of record — it only appends atoms to its own logs (entries,
resolutions), which Emise's ticks drain.

Two headless credentials stand beside the session, each fail-closed
and each authorizing exactly its own legs (qexo dispatch-core spec
§10.4): the drain token (X-Drain-Token) reads the two queue logs and
nothing else; the qexo service token (X-Qexo-Token) appends entries
and records resolutions — the ratified Q2 scope, bound to this
register (Will's scope) — and nothing else. Atoms written under the
qexo token record ``user`` as the token's identity, ``qexo``.
"""

import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path

from .ldap_auth import LdapUnavailable
from .webauthn_auth import WebAuthnError, b64url
from webauthn.helpers import base64url_to_bytes

SESSION_COOKIE = "regsvc_session"
PREAUTH_COOKIE = "regsvc_pre"
MAX_BODY = 64 * 1024
MAX_ENTRY_CHARS = 2000
MAX_NOTE_CHARS = 4000
CLOSE_PATH = re.compile(r"^/api/items/(\d+)/(done|cancel)$")


def _json(status, obj, extra_headers=None):
    body = json.dumps(obj).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Cache-Control": "no-store"}
    if extra_headers:
        headers.update(extra_headers)
    return status, headers, body


def _err(status, message):
    return _json(status, {"error": message})


class RegisterApp:
    def __init__(self, *, entries_log, resolutions_log, credentials,
                 sessions, ldap_auth, ceremonies, secret,
                 numbers_file=None, session_ttl=7 * 24 * 3600,
                 preauth_ttl=300, drain_token=None, drain_user=None,
                 numbers_owner=None, qexo_token=None):
        self.entries = entries_log
        self.resolutions = resolutions_log
        self.credentials = credentials
        self.sessions = sessions
        self.ldap = ldap_auth
        self.ceremonies = ceremonies
        self.secret = secret
        self.drain_token = drain_token
        # Per-user scoping: every queue read/write happens inside one
        # login's scope. A session's scope is its own uid. The drain
        # token has no session, so its scope is the configured
        # drain_user — the login on whose behalf drains run. With no
        # drain_user configured the token authorizes nothing.
        self.drain_user = drain_user
        # Owner assigned to register numbers listed in the legacy
        # flat-list numbers file (a bare [n, ...] carries no owner;
        # the object form {"n": uid} names each number's owner).
        self.numbers_owner = numbers_owner
        self.qexo_token = qexo_token
        self.numbers_file = Path(numbers_file) if numbers_file else None
        self.session_ttl = session_ttl
        self.preauth_ttl = preauth_ttl
        self._preauth = {}  # token -> {uid, challenge(b64url), expires}
        self._numbers_cache = None
        self._numbers_mtime = None

    # -- signing / cookies --------------------------------------------
    def _sign(self, value):
        mac = hmac.new(self.secret, value.encode("utf-8"),
                       hashlib.sha256).hexdigest()
        return f"{value}.{mac}"

    def _unsign(self, signed):
        if not signed or "." not in signed:
            return None
        value, _, mac = signed.rpartition(".")
        expected = hmac.new(self.secret, value.encode("utf-8"),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            return None
        return value

    @staticmethod
    def _cookie_header(name, value, max_age):
        return (f"{name}={value}; Path=/api; Max-Age={max_age}; "
                f"HttpOnly; Secure; SameSite=Lax")

    def _cookies(self, headers):
        raw = headers.get("Cookie") or headers.get("cookie") or ""
        out = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def _session(self, headers):
        """(session_id, record) or (None, None)."""
        signed = self._cookies(headers).get(SESSION_COOKIE)
        sid = self._unsign(signed) if signed else None
        if not sid:
            return None, None
        rec = self.sessions.get(sid)
        if rec is None:
            return None, None
        return sid, rec

    def _require_session(self, headers):
        sid, rec = self._session(headers)
        if rec is None:
            return None, None, _err(401, "not logged in")
        return sid, rec, None

    def _require_csrf(self, headers, rec):
        token = headers.get("X-CSRF-Token") or headers.get("x-csrf-token")
        if not token or not hmac.compare_digest(token, rec.get("csrf", "")):
            return _err(403, "missing or bad CSRF token")
        return None

    def _start_session(self, uid):
        sid = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = int(time.time())
        self.sessions.create(sid, {
            "uid": uid, "created": now, "expires": now + self.session_ttl,
            "csrf": csrf, "reg_challenge": None,
        })
        cookie = self._cookie_header(SESSION_COOKIE, self._sign(sid),
                                     self.session_ttl)
        return {"user": uid, "csrf": csrf}, {"Set-Cookie": cookie}

    # -- register numbers (for Done validation) ------------------------
    def _known_numbers(self):
        """Map of open register number -> owning uid, or None if the
        numbers file is unavailable.

        Two file shapes are accepted: the scoped object form
        ``{"167": "wbic16", ...}`` (each number names its owner), and
        the legacy flat list ``[167, ...]`` whose numbers all belong
        to the configured ``numbers_owner`` (None = owned by nobody,
        so nothing can be closed against them — fail closed).
        """
        if self.numbers_file is None:
            return None
        try:
            mtime = self.numbers_file.stat().st_mtime
            if self._numbers_cache is None or mtime != self._numbers_mtime:
                data = json.loads(
                    self.numbers_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    owners = {}
                    for k, v in data.items():
                        owners[int(k)] = v if isinstance(v, str) else None
                    self._numbers_cache = owners
                elif isinstance(data, list):
                    self._numbers_cache = {
                        int(n): self.numbers_owner for n in data}
                else:
                    return None
                self._numbers_mtime = mtime
            return self._numbers_cache
        except Exception:
            return None

    # -- routing ---------------------------------------------------------
    def handle(self, method, path, headers, body=b""):
        try:
            return self._route(method, path, headers, body)
        except Exception:  # never leak a stack; never half-answer
            return _err(500, "internal error")

    def _route(self, method, path, headers, body):
        if len(body) > MAX_BODY:
            return _err(413, "body too large")
        path_only, _, query = path.partition("?")
        params = {}
        for pair in query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v

        if method == "GET" and path_only == "/api/health":
            return _json(200, {"ok": True})
        if method == "GET" and path_only == "/api/session":
            _, rec = self._session(headers)
            if rec is None:
                return _json(200, {"user": None, "csrf": None})
            return _json(200, {"user": rec["uid"], "csrf": rec["csrf"]})
        if method == "POST" and path_only == "/api/login":
            return self._login(body)
        if method == "POST" and path_only == "/api/logout":
            return self._logout(headers)
        if method == "POST" and path_only == "/api/entries":
            return self._add_entry(headers, body)
        if method == "GET" and path_only == "/api/entries/pending":
            return self._list_log(headers, self.entries, params)
        if method == "GET" and path_only == "/api/resolutions":
            return self._list_log(headers, self.resolutions, params)
        m = CLOSE_PATH.match(path_only)
        if method == "POST" and m:
            outcome = "done" if m.group(2) == "done" else "cancelled"
            return self._close_item(headers, body, int(m.group(1)),
                                    outcome)
        if method == "POST" and path_only == "/api/webauthn/register/options":
            return self._wa_register_options(headers)
        if method == "POST" and path_only == "/api/webauthn/register/verify":
            return self._wa_register_verify(headers, body)
        if method == "POST" and path_only == "/api/webauthn/login/options":
            return self._wa_login_options(body)
        if method == "POST" and path_only == "/api/webauthn/login/verify":
            return self._wa_login_verify(headers, body)
        return _err(404, "no such endpoint")

    @staticmethod
    def _body_json(body):
        try:
            return json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            return None

    # -- password login ---------------------------------------------------
    def _login(self, body):
        data = self._body_json(body)
        if data is None:
            return _err(400, "bad JSON")
        uid = (data.get("uid") or "").strip()
        password = data.get("password") or ""
        if not uid or not password:
            return _err(400, "uid and password required")
        try:
            who = self.ldap.authenticate(uid, password)
        except LdapUnavailable:
            return _err(503, "directory unavailable")
        if who is None:
            return _err(401, "invalid credentials")
        payload, hdrs = self._start_session(who)
        return _json(200, payload, hdrs)

    def _logout(self, headers):
        sid, rec, err = self._require_session(headers)
        if err:
            return err
        err = self._require_csrf(headers, rec)
        if err:
            return err
        self.sessions.delete(sid)
        cookie = self._cookie_header(SESSION_COOKIE, "", 0)
        return _json(200, {"user": None}, {"Set-Cookie": cookie})

    # -- entries & resolutions ---------------------------------------------
    def _add_entry(self, headers, body):
        # The qexo service token may also append (ratified
        # Q2 scope): items born on the phone appear in the
        # register web view. The atom records the token's
        # identity as its user — a body claiming another
        # user is ignored, never trusted.
        if self._qexo_authorized(headers):
            uid = "qexo"
        else:
            _, rec, err = self._require_session(headers)
            if err:
                return err
            err = self._require_csrf(headers, rec)
            if err:
                return err
            uid = rec["uid"]
        data = self._body_json(body)
        if data is None:
            return _err(400, "bad JSON")
        text = (data.get("text") or "").strip()
        if not text:
            return _err(400, "text required")
        if len(text) > MAX_ENTRY_CHARS:
            return _err(400, "text too long")
        atom = self.entries.append(
            {"type": "entry", "text": text, "user": uid})
        return _json(201, {"ok": True, "seq": atom["seq"]})

    def _drain_authorized(self, headers):
        """The two queue reads also accept the drain token (Emise's
        ticks drain headlessly; they cannot hold a browser session).
        The token authorizes NOTHING else."""
        if not self.drain_token:
            return False
        token = headers.get("X-Drain-Token") or \
            headers.get("x-drain-token")
        return bool(token) and hmac.compare_digest(token, self.drain_token)

    def _qexo_authorized(self, headers):
        """The qexo service token (dispatch-core spec §10.4):
        authorizes POST /api/entries and POST
        /api/items/{n}/done|cancel on this register — Will's
        scope — recording ``user`` as the token's identity.
        Fail-closed when unset; authorizes NOTHING else (no
        reads, no login, no session powers), and its scope
        is not widenable by configuration (§10.5)."""
        if not self.qexo_token:
            return False
        token = headers.get("X-Qexo-Token") or \
            headers.get("x-qexo-token")
        return bool(token) and hmac.compare_digest(token, self.qexo_token)

    def _list_log(self, headers, log, params):
        """Queue reads are scoped to one login: a session sees only
        its own atoms; the drain token sees only the configured
        drain_user's atoms (per-user drain)."""
        if self._drain_authorized(headers):
            if not self.drain_user:
                return _err(401, "drain token is not scoped to a user")
            scope = self.drain_user
        else:
            _, rec, err = self._require_session(headers)
            if err:
                return err
            scope = rec["uid"]
        try:
            after = int(params.get("after_seq", "0"))
        except ValueError:
            return _err(400, "after_seq must be an integer")
        atoms = log.read_all(after_seq=after, user=scope)
        return _json(200, {"atoms": atoms, "last_seq": log.last_seq})

    def _close_item(self, headers, body, number, outcome):
        """Shared handler for /done (outcome "done") and /cancel
        (outcome "cancelled") — identical auth, CSRF, number, and
        note contracts; only the recorded outcome differs. The
        qexo service token is the second authorized writer
        (§10.4): same number and note contracts, no session, and
        the atom records the token's identity as its user."""
        if self._qexo_authorized(headers):
            uid = "qexo"
        else:
            _, rec, err = self._require_session(headers)
            if err:
                return err
            err = self._require_csrf(headers, rec)
            if err:
                return err
            uid = rec["uid"]
        # Optional close rationale: {"note": "..."} captured by the
        # page's close dialog. No body (or an empty object) is exactly
        # the pre-dialog behavior — a bare resolution atom.
        data = self._body_json(body)
        if data is None:
            return _err(400, "bad JSON")
        if not isinstance(data, dict):
            return _err(400, "body must be a JSON object")
        note = data.get("note")
        if note is not None:
            if not isinstance(note, str):
                return _err(400, "note must be a string")
            note = note.strip()
            if len(note) > MAX_NOTE_CHARS:
                return _err(400, "note too long")
        known = self._known_numbers()
        if known is None:
            return _err(503, "register numbers unavailable")
        # Per-user scoping: a number can be closed only by its owner.
        # Unknown, unowned, and other-owned numbers are
        # indistinguishable — all 404, no existence leak.
        if known.get(number) != rec["uid"]:
            return _err(404, "unknown register number")
        fields = {"type": "resolution", "register_number": number,
                  "user": uid, "outcome": outcome}
        if note:
            fields["note"] = note
        atom = self.resolutions.append(fields)
        return _json(201, {"ok": True, "seq": atom["seq"]})

    # -- WebAuthn: registration (requires a session) ------------------------
    def _wa_register_options(self, headers):
        sid, rec, err = self._require_session(headers)
        if err:
            return err
        err = self._require_csrf(headers, rec)
        if err:
            return err
        existing = self.credentials.list_for(rec["uid"])
        challenge, options_json = self.ceremonies.registration_options(
            rec["uid"], existing)
        self.sessions.update(sid, reg_challenge=b64url(challenge))
        return 200, {"Content-Type": "application/json",
                     "Cache-Control": "no-store"}, \
            options_json.encode("utf-8")

    def _wa_register_verify(self, headers, body):
        sid, rec, err = self._require_session(headers)
        if err:
            return err
        err = self._require_csrf(headers, rec)
        if err:
            return err
        data = self._body_json(body)
        if data is None or "credential" not in data:
            return _err(400, "credential required")
        challenge_b64 = rec.get("reg_challenge")
        if not challenge_b64:
            return _err(400, "no registration in progress")
        self.sessions.update(sid, reg_challenge=None)  # one-shot
        try:
            cred = self.ceremonies.verify_registration(
                data["credential"], base64url_to_bytes(challenge_b64))
        except WebAuthnError:
            return _err(400, "registration verification failed")
        cred["transports"] = data["credential"].get("response", {}).get(
            "transports") or data["credential"].get("transports") or []
        cred["created_ts"] = int(time.time())
        self.credentials.add(rec["uid"], cred)
        return _json(201, {"ok": True})

    # -- WebAuthn: login ------------------------------------------------------
    def _wa_login_options(self, body):
        data = self._body_json(body)
        if data is None:
            return _err(400, "bad JSON")
        uid = (data.get("uid") or "").strip()
        creds = self.credentials.list_for(uid) if uid else []
        if not creds:
            return _err(404, "no passkeys enrolled for that user")
        challenge, options_json = self.ceremonies.authentication_options(
            creds)
        token = secrets.token_urlsafe(24)
        self._preauth[token] = {
            "uid": uid, "challenge": b64url(challenge),
            "expires": int(time.time()) + self.preauth_ttl,
        }
        cookie = self._cookie_header(PREAUTH_COOKIE, self._sign(token),
                                     self.preauth_ttl)
        return 200, {"Content-Type": "application/json",
                     "Cache-Control": "no-store",
                     "Set-Cookie": cookie}, options_json.encode("utf-8")

    def _wa_login_verify(self, headers, body):
        signed = self._cookies(headers).get(PREAUTH_COOKIE)
        token = self._unsign(signed) if signed else None
        pre = self._preauth.pop(token, None) if token else None
        if pre is None or pre["expires"] <= int(time.time()):
            return _err(401, "no passkey login in progress")
        data = self._body_json(body)
        if data is None or "credential" not in data:
            return _err(400, "credential required")
        cred_id = data["credential"].get("id")
        stored = self.credentials.find(pre["uid"], cred_id) if cred_id \
            else None
        if stored is None:
            return _err(401, "unknown credential")
        try:
            new_count = self.ceremonies.verify_authentication(
                data["credential"],
                base64url_to_bytes(pre["challenge"]), stored)
        except WebAuthnError:
            return _err(401, "passkey verification failed")
        self.credentials.update_sign_count(pre["uid"], cred_id, new_count)
        payload, hdrs = self._start_session(pre["uid"])
        return _json(200, payload, hdrs)
