"""The qexo service token's legs (dispatch-core spec §10.4, Q2).

Positive: the token appends entries and records resolutions on
this register, with atoms recording the token's identity ("qexo").
Negative: the token reads nothing, logs in nowhere, and widens to
nothing; the drain token writes nothing; wrong or absent tokens
refuse; an unset token fails closed. The session path is asserted
unchanged — the token is a second writer beside it, not a change
to it.
"""

import json
import tempfile
import unittest
from pathlib import Path

from regsvc.app import RegisterApp
from regsvc.store import CredentialStore, JsonlLog, SessionStore

from test_app import FakeCeremonies, FakeLdap, SECRET

DRAIN = "drain-test-token"
QEXO = "qexo-test-token"


class Client:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def call(self, method, path, body=None, headers=None, csrf=None):
        hdrs = dict(headers or {})
        if self.cookies:
            hdrs["Cookie"] = "; ".join(
                f"{k}={v}" for k, v in self.cookies.items())
        if csrf:
            hdrs["X-CSRF-Token"] = csrf
        raw = json.dumps(body).encode() if body is not None else b""
        status, resp_headers, resp_body = self.app.handle(
            method, path, hdrs, raw)
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


def make_app(tmp, numbers=(9, 10, 21), qexo_token=QEXO,
             drain_token=DRAIN, numbers_file=True):
    numbers_path = Path(tmp) / "register-numbers.json"
    if numbers_file:
        # Scoped object form (per-user scoping): every number
        # belongs to the session user "will" — who is also this
        # fixture's drain scope and the qexo token's scope owner.
        numbers_path.write_text(json.dumps(
            {str(n): "will" for n in numbers}))
    return RegisterApp(
        entries_log=JsonlLog(Path(tmp) / "pending-entries.jsonl"),
        resolutions_log=JsonlLog(Path(tmp) / "resolutions.jsonl"),
        credentials=CredentialStore(Path(tmp) / "credentials.json"),
        sessions=SessionStore(Path(tmp) / "sessions.json"),
        ldap_auth=FakeLdap({"will": "hunter2"}),
        ceremonies=FakeCeremonies(),
        secret=SECRET,
        numbers_file=numbers_path,
        drain_token=drain_token,
        drain_user="will",
        qexo_token=qexo_token,
        qexo_user="will",
    )


def read_log(tmp, name):
    path = Path(tmp) / name
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text().splitlines() if line.strip()]


class QexoTokenTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(self.tmp)
        self.client = Client(self.app)

    def qexo(self):
        return {"X-Qexo-Token": QEXO}

    def drain(self):
        return {"X-Drain-Token": DRAIN}


class TestPositiveLegs(QexoTokenTestCase):
    def test_token_appends_an_entry_as_qexo(self):
        status, body, _ = self.client.call(
            "POST", "/api/entries", {"text": "phone-born item"},
            headers=self.qexo())
        self.assertEqual(status, 201)
        self.assertEqual(body["seq"], 1)
        atoms = read_log(self.tmp, "pending-entries.jsonl")
        self.assertEqual(len(atoms), 1)
        self.assertEqual(atoms[0]["user"], "qexo")
        self.assertEqual(atoms[0]["text"], "phone-born item")
        # and it stands in the log the register's readers drain —
        # the surface the web view is generated from.
        status, body, _ = self.client.call(
            "GET", "/api/entries/pending?after_seq=0",
            headers=self.drain())
        self.assertEqual(status, 200)
        self.assertEqual([a["text"] for a in body["atoms"]],
                         ["phone-born item"])

    def test_token_records_done_and_cancel_with_note(self):
        status, body, _ = self.client.call(
            "POST", "/api/items/9/done", {}, headers=self.qexo())
        self.assertEqual((status, body["seq"]), (201, 1))
        status, body, _ = self.client.call(
            "POST", "/api/items/10/cancel", {"note": "moot"},
            headers=self.qexo())
        self.assertEqual((status, body["seq"]), (201, 2))
        atoms = read_log(self.tmp, "resolutions.jsonl")
        self.assertEqual(
            [(a["register_number"], a["outcome"], a["user"])
             for a in atoms],
            [(9, "done", "qexo"), (10, "cancelled", "qexo")])
        self.assertEqual(atoms[1]["note"], "moot")

    def test_body_cannot_spoof_another_user(self):
        status, _, _ = self.client.call(
            "POST", "/api/entries",
            {"text": "x", "user": "mallory"}, headers=self.qexo())
        self.assertEqual(status, 201)
        atoms = read_log(self.tmp, "pending-entries.jsonl")
        self.assertEqual(atoms[0]["user"], "qexo")


class TestNegativeLegs(QexoTokenTestCase):
    def test_wrong_and_absent_tokens_refuse(self):
        for hdrs in ({"X-Qexo-Token": "wrong"}, {}):
            status, _, _ = self.client.call(
                "POST", "/api/entries", {"text": "x"}, headers=hdrs)
            self.assertEqual(status, 401)
            status, _, _ = self.client.call(
                "POST", "/api/items/9/done", {}, headers=hdrs)
            self.assertEqual(status, 401)
        self.assertEqual(read_log(self.tmp, "pending-entries.jsonl"),
                         [])
        self.assertEqual(read_log(self.tmp, "resolutions.jsonl"), [])

    def test_drain_token_cannot_write(self):
        status, _, _ = self.client.call(
            "POST", "/api/entries", {"text": "x"},
            headers=self.drain())
        self.assertEqual(status, 401)
        status, _, _ = self.client.call(
            "POST", "/api/items/9/done", {}, headers=self.drain())
        self.assertEqual(status, 401)

    def test_qexo_token_cannot_read(self):
        for path in ("/api/entries/pending?after_seq=0",
                     "/api/resolutions?after_seq=0"):
            status, _, _ = self.client.call(
                "GET", path, headers=self.qexo())
            self.assertEqual(status, 401)

    def test_qexo_token_grants_no_login(self):
        # Presented at the login endpoint, the token is not a
        # credential: a wrong password still refuses, no
        # session is minted, and the session probe stays
        # logged out for a token-only caller.
        status, _, headers = self.client.call(
            "POST", "/api/login",
            {"uid": "will", "password": "wrong"},
            headers=self.qexo())
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)
        fresh = Client(self.app)
        status, body, _ = fresh.call(
            "GET", "/api/session", headers=self.qexo())
        self.assertEqual((status, body["user"]), (200, None))

    def test_unset_qexo_token_fails_closed(self):
        app = make_app(self.tmp, qexo_token=None)
        client = Client(app)
        status, _, _ = client.call(
            "POST", "/api/entries", {"text": "x"},
            headers={"X-Qexo-Token": "anything"})
        self.assertEqual(status, 401)
        status, _, _ = client.call(
            "POST", "/api/items/9/done", {},
            headers={"X-Qexo-Token": "anything"})
        self.assertEqual(status, 401)

    def test_number_and_note_contracts_still_apply(self):
        status, body, _ = self.client.call(
            "POST", "/api/items/999/done", {}, headers=self.qexo())
        self.assertEqual((status, body["error"]),
                         (404, "unknown register number"))
        status, _, _ = self.client.call(
            "POST", "/api/items/9/cancel", {"note": "n" * 4001},
            headers=self.qexo())
        self.assertEqual(status, 400)
        app = make_app(tempfile.mkdtemp(), numbers_file=False)
        client = Client(app)
        status, body, _ = client.call(
            "POST", "/api/items/9/done", {}, headers=self.qexo())
        self.assertEqual((status, body["error"]),
                         (503, "register numbers unavailable"))


class TestSessionPathUnchanged(QexoTokenTestCase):
    def test_session_append_and_close_still_record_the_user(self):
        status, body, _ = self.client.call(
            "POST", "/api/login",
            {"uid": "will", "password": "hunter2"})
        self.assertEqual(status, 200)
        csrf = body["csrf"]
        status, _, _ = self.client.call(
            "POST", "/api/entries", {"text": "browser-born"},
            csrf=csrf)
        self.assertEqual(status, 201)
        status, _, _ = self.client.call(
            "POST", "/api/items/21/done", {}, csrf=csrf)
        self.assertEqual(status, 201)
        entries = read_log(self.tmp, "pending-entries.jsonl")
        resolutions = read_log(self.tmp, "resolutions.jsonl")
        self.assertEqual(entries[0]["user"], "will")
        self.assertEqual(resolutions[0]["user"], "will")


if __name__ == "__main__":
    unittest.main()
