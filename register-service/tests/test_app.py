import json
import tempfile
import unittest
from pathlib import Path

from regsvc.app import RegisterApp
from regsvc.ldap_auth import LdapUnavailable
from regsvc.store import CredentialStore, JsonlLog, SessionStore
from regsvc.webauthn_auth import WebAuthnError

SECRET = b"test-secret-test-secret-test-secret-0123456789"


class FakeLdap:
    def __init__(self, valid=None, down=False):
        self.valid = valid or {}
        self.down = down

    def authenticate(self, uid, password):
        if self.down:
            raise LdapUnavailable("directory down")
        if password and self.valid.get(uid) == password:
            return uid
        return None


class FakeCeremonies:
    def __init__(self):
        self.fail_reg = False
        self.fail_auth = False

    def registration_options(self, uid, existing):
        return b"reg-challenge", '{"challenge":"reg"}'

    def verify_registration(self, credential, challenge):
        if self.fail_reg:
            raise WebAuthnError("bad attestation")
        assert challenge == b"reg-challenge", challenge
        return {"credential_id": "cred-1", "public_key": "pk-1",
                "sign_count": 0}

    def authentication_options(self, credentials):
        return b"auth-challenge", '{"challenge":"auth"}'

    def verify_authentication(self, credential, challenge, stored):
        if self.fail_auth:
            raise WebAuthnError("bad assertion")
        assert challenge == b"auth-challenge", challenge
        return stored["sign_count"] + 1


class Client:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def call(self, method, path, body=None, csrf=None, raw_cookies=None):
        headers = {}
        cookies = self.cookies if raw_cookies is None else raw_cookies
        if cookies:
            headers["Cookie"] = "; ".join(
                f"{k}={v}" for k, v in cookies.items())
        if csrf:
            headers["X-CSRF-Token"] = csrf
        raw = json.dumps(body).encode() if body is not None else b""
        status, resp_headers, resp_body = self.app.handle(
            method, path, headers, raw)
        if "Set-Cookie" in resp_headers:
            pair = resp_headers["Set-Cookie"].split(";")[0]
            k, _, v = pair.partition("=")
            if v:
                self.cookies[k] = v
            else:
                self.cookies.pop(k, None)
        try:
            parsed = json.loads(resp_body.decode())
        except Exception:
            parsed = None
        return status, parsed, resp_headers


def make_app(tmp, numbers=(9, 10, 21), ldap=None, ceremonies=None,
             numbers_file=True):
    numbers_path = Path(tmp) / "register-numbers.json"
    if numbers_file:
        numbers_path.write_text(json.dumps(list(numbers)))
    return RegisterApp(
        entries_log=JsonlLog(Path(tmp) / "pending-entries.jsonl"),
        resolutions_log=JsonlLog(Path(tmp) / "resolutions.jsonl"),
        credentials=CredentialStore(Path(tmp) / "credentials.json"),
        sessions=SessionStore(Path(tmp) / "sessions.json"),
        ldap_auth=ldap or FakeLdap({"will": "hunter2"}),
        ceremonies=ceremonies or FakeCeremonies(),
        secret=SECRET,
        numbers_file=numbers_path,
    )


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(self.tmp)
        self.client = Client(self.app)

    def login(self):
        status, body, _ = self.client.call(
            "POST", "/api/login", {"uid": "will", "password": "hunter2"})
        assert status == 200, body
        return body["csrf"]


class TestPasswordLogin(AppTestCase):
    def test_session_starts_logged_out(self):
        status, body, _ = self.client.call("GET", "/api/session")
        self.assertEqual((status, body["user"]), (200, None))

    def test_bad_password_401_no_cookie(self):
        status, body, headers = self.client.call(
            "POST", "/api/login", {"uid": "will", "password": "nope"})
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)

    def test_ldap_down_503(self):
        self.app.ldap.down = True
        status, _, _ = self.client.call(
            "POST", "/api/login", {"uid": "will", "password": "hunter2"})
        self.assertEqual(status, 503)

    def test_login_then_session(self):
        csrf = self.login()
        self.assertTrue(csrf)
        status, body, _ = self.client.call("GET", "/api/session")
        self.assertEqual(body["user"], "will")

    def test_tampered_cookie_rejected(self):
        self.login()
        bad = dict(self.client.cookies)
        sid = bad["regsvc_session"]
        bad["regsvc_session"] = sid[:-2] + "xx"
        status, body, _ = self.client.call(
            "GET", "/api/session", raw_cookies=bad)
        self.assertIsNone(body["user"])

    def test_logout(self):
        csrf = self.login()
        status, _, _ = self.client.call("POST", "/api/logout", {},
                                        csrf=csrf)
        self.assertEqual(status, 200)
        status, body, _ = self.client.call("GET", "/api/session")
        self.assertIsNone(body["user"])


class TestEntries(AppTestCase):
    def test_entries_require_auth(self):
        status, _, _ = self.client.call("POST", "/api/entries",
                                        {"text": "hello"})
        self.assertEqual(status, 401)
        status, _, _ = self.client.call("GET", "/api/entries/pending")
        self.assertEqual(status, 401)

    def test_entries_require_csrf(self):
        self.login()
        status, _, _ = self.client.call("POST", "/api/entries",
                                        {"text": "hello"})
        self.assertEqual(status, 403)

    def test_add_and_list_entries(self):
        csrf = self.login()
        status, body, _ = self.client.call(
            "POST", "/api/entries", {"text": "first wait"}, csrf=csrf)
        self.assertEqual((status, body["seq"]), (201, 1))
        status, body, _ = self.client.call(
            "POST", "/api/entries", {"text": "second wait"}, csrf=csrf)
        self.assertEqual((status, body["seq"]), (201, 2))
        status, body, _ = self.client.call("GET", "/api/entries/pending")
        atoms = body["atoms"]
        self.assertEqual([a["text"] for a in atoms],
                         ["first wait", "second wait"])
        self.assertTrue(all(a["user"] == "will" for a in atoms))
        status, body, _ = self.client.call(
            "GET", "/api/entries/pending?after_seq=1")
        self.assertEqual([a["text"] for a in body["atoms"]],
                         ["second wait"])

    def test_empty_and_huge_entries_rejected(self):
        csrf = self.login()
        status, _, _ = self.client.call("POST", "/api/entries",
                                        {"text": "   "}, csrf=csrf)
        self.assertEqual(status, 400)
        status, _, _ = self.client.call(
            "POST", "/api/entries", {"text": "x" * 2001}, csrf=csrf)
        self.assertEqual(status, 400)


class TestDone(AppTestCase):
    def test_done_records_resolution_atom(self):
        csrf = self.login()
        status, body, _ = self.client.call(
            "POST", "/api/items/9/done", {}, csrf=csrf)
        self.assertEqual((status, body["seq"]), (201, 1))
        status, body, _ = self.client.call("GET", "/api/resolutions")
        atoms = body["atoms"]
        self.assertEqual(len(atoms), 1)
        self.assertEqual(atoms[0]["register_number"], 9)
        self.assertEqual(atoms[0]["user"], "will")

    def test_done_twice_records_both_atoms(self):
        # Idempotency lives at drain time; the log keeps both events.
        csrf = self.login()
        for _ in range(2):
            status, _, _ = self.client.call(
                "POST", "/api/items/9/done", {}, csrf=csrf)
            self.assertEqual(status, 201)
        status, body, _ = self.client.call("GET", "/api/resolutions")
        self.assertEqual(len(body["atoms"]), 2)

    def test_done_unknown_number_404(self):
        csrf = self.login()
        status, _, _ = self.client.call(
            "POST", "/api/items/999/done", {}, csrf=csrf)
        self.assertEqual(status, 404)

    def test_done_requires_auth_and_csrf(self):
        status, _, _ = self.client.call("POST", "/api/items/9/done", {})
        self.assertEqual(status, 401)
        self.login()
        status, _, _ = self.client.call("POST", "/api/items/9/done", {})
        self.assertEqual(status, 403)

    def test_done_numbers_file_missing_503(self):
        app = make_app(tempfile.mkdtemp(), numbers_file=False)
        client = Client(app)
        status, body, _ = client.call(
            "POST", "/api/login", {"uid": "will", "password": "hunter2"})
        csrf = body["csrf"]
        status, _, _ = client.call("POST", "/api/items/9/done", {},
                                   csrf=csrf)
        self.assertEqual(status, 503)


class TestPasskeys(AppTestCase):
    def enroll(self):
        csrf = self.login()
        status, _, _ = self.client.call(
            "POST", "/api/webauthn/register/options", {}, csrf=csrf)
        assert status == 200
        status, body, _ = self.client.call(
            "POST", "/api/webauthn/register/verify",
            {"credential": {"id": "cred-1", "response": {}}}, csrf=csrf)
        assert status == 201, body
        return csrf

    def test_register_options_requires_session(self):
        status, _, _ = self.client.call(
            "POST", "/api/webauthn/register/options", {})
        self.assertEqual(status, 401)

    def test_verify_without_options_400(self):
        csrf = self.login()
        status, _, _ = self.client.call(
            "POST", "/api/webauthn/register/verify",
            {"credential": {"id": "cred-1", "response": {}}}, csrf=csrf)
        self.assertEqual(status, 400)

    def test_enroll_stores_credential(self):
        self.enroll()
        creds = self.app.credentials.list_for("will")
        self.assertEqual(len(creds), 1)
        self.assertEqual(creds[0]["credential_id"], "cred-1")

    def test_enroll_failure_stores_nothing(self):
        self.app.ceremonies.fail_reg = True
        csrf = self.login()
        self.client.call("POST", "/api/webauthn/register/options", {},
                         csrf=csrf)
        status, _, _ = self.client.call(
            "POST", "/api/webauthn/register/verify",
            {"credential": {"id": "cred-1", "response": {}}}, csrf=csrf)
        self.assertEqual(status, 400)
        self.assertEqual(self.app.credentials.list_for("will"), [])

    def test_login_options_unknown_user_404(self):
        status, _, _ = self.client.call(
            "POST", "/api/webauthn/login/options", {"uid": "ghost"})
        self.assertEqual(status, 404)

    def test_passkey_login_happy_path(self):
        self.enroll()
        fresh = Client(self.app)  # prove the passkey itself logs in
        status, _, _ = fresh.call(
            "POST", "/api/webauthn/login/options", {"uid": "will"})
        self.assertEqual(status, 200)
        status, body, _ = fresh.call(
            "POST", "/api/webauthn/login/verify",
            {"credential": {"id": "cred-1", "response": {}}})
        self.assertEqual(status, 200)
        self.assertEqual(body["user"], "will")
        # sign count advanced and persisted
        self.assertEqual(
            self.app.credentials.find("will", "cred-1")["sign_count"], 1)
        status, body, _ = fresh.call("GET", "/api/session")
        self.assertEqual(body["user"], "will")

    def test_passkey_login_bad_assertion_401(self):
        self.enroll()
        self.app.ceremonies.fail_auth = True
        fresh = Client(self.app)
        fresh.call("POST", "/api/webauthn/login/options", {"uid": "will"})
        status, _, _ = fresh.call(
            "POST", "/api/webauthn/login/verify",
            {"credential": {"id": "cred-1", "response": {}}})
        self.assertEqual(status, 401)
        status, body, _ = fresh.call("GET", "/api/session")
        self.assertIsNone(body["user"])

    def test_passkey_verify_without_options_401(self):
        status, _, _ = self.client.call(
            "POST", "/api/webauthn/login/verify",
            {"credential": {"id": "cred-1", "response": {}}})
        self.assertEqual(status, 401)

    def test_passkey_unknown_credential_401(self):
        self.enroll()
        self.client.call("POST", "/api/webauthn/login/options",
                         {"uid": "will"})
        status, _, _ = self.client.call(
            "POST", "/api/webauthn/login/verify",
            {"credential": {"id": "forged", "response": {}}})
        self.assertEqual(status, 401)


class TestDrainToken(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = RegisterApp(
            entries_log=JsonlLog(Path(self.tmp) / "e.jsonl"),
            resolutions_log=JsonlLog(Path(self.tmp) / "r.jsonl"),
            credentials=CredentialStore(Path(self.tmp) / "c.json"),
            sessions=SessionStore(Path(self.tmp) / "s.json"),
            ldap_auth=FakeLdap({"will": "hunter2"}),
            ceremonies=FakeCeremonies(),
            secret=SECRET,
            numbers_file=None,
            drain_token="drain-secret-token",
        )
        self.app.entries.append({"type": "entry", "text": "queued",
                                 "user": "will"})

    def call(self, method, path, headers=None, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        status, _, resp = self.app.handle(method, path, headers or {}, raw)
        return status, json.loads(resp.decode())

    def test_drain_token_reads_both_logs(self):
        h = {"X-Drain-Token": "drain-secret-token"}
        status, body = self.call("GET", "/api/entries/pending", h)
        self.assertEqual(status, 200)
        self.assertEqual(body["atoms"][0]["text"], "queued")
        status, body = self.call("GET", "/api/resolutions", h)
        self.assertEqual(status, 200)

    def test_wrong_drain_token_401(self):
        status, _ = self.call("GET", "/api/entries/pending",
                              {"X-Drain-Token": "nope"})
        self.assertEqual(status, 401)

    def test_drain_token_cannot_write(self):
        h = {"X-Drain-Token": "drain-secret-token"}
        status, _ = self.call("POST", "/api/entries", h,
                              {"text": "forged"})
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
