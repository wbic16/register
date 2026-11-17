"""The qexo token under per-user scoping (the #9/#10 composition).

The rule under test: the qexo service token answers to the same
ownership rule as a session — a register number can be closed only
by its owner — evaluated against the token's configured scope
owner (``qexo_user``), never against its recorded identity
("qexo" owns no numbers) and never by exemption. Its atoms still
record user "qexo", and reads scoped to the scope owner include
them; no other scope sees them.

Also under test: the two 404 causes at the close path — unknown
number vs known number outside the caller's scope — stay
indistinguishable to the caller (same status, same body) and
distinguishable in the service log, so a scoping fault can no
longer masquerade as a credential failure.
"""

import json
import tempfile
import unittest
from pathlib import Path

from regsvc.app import RegisterApp
from regsvc.store import CredentialStore, JsonlLog, SessionStore

from test_app import FakeCeremonies, FakeLdap, SECRET
from test_qexo_token import Client, read_log

DRAIN = "drain-test-token"
QEXO = "qexo-test-token"
NUMBERS = {"181": "will", "182": "amy"}


def make_app(tmp, qexo_user="will", logger=None):
    numbers_path = Path(tmp) / "register-numbers.json"
    numbers_path.write_text(json.dumps(NUMBERS))
    return RegisterApp(
        entries_log=JsonlLog(Path(tmp) / "pending-entries.jsonl"),
        resolutions_log=JsonlLog(Path(tmp) / "resolutions.jsonl"),
        credentials=CredentialStore(Path(tmp) / "credentials.json"),
        sessions=SessionStore(Path(tmp) / "sessions.json"),
        ldap_auth=FakeLdap({"will": "hunter2", "amy": "hunter3"}),
        ceremonies=FakeCeremonies(),
        secret=SECRET,
        numbers_file=numbers_path,
        drain_token=DRAIN,
        drain_user="will",
        qexo_token=QEXO,
        qexo_user=qexo_user,
        logger=logger,
    )


class ScopeOwnerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log_lines = []
        self.app = make_app(self.tmp, logger=self.log_lines.append)
        self.client = Client(self.app)

    def qexo(self):
        return {"X-Qexo-Token": QEXO}

    def login(self, uid, password):
        client = Client(self.app)
        status, body, _ = client.call(
            "POST", "/api/login", {"uid": uid, "password": password})
        self.assertEqual(status, 200)
        return client, body["csrf"]


class TestQexoClosesInScope(ScopeOwnerCase):
    def test_qexo_closes_number_in_its_scope(self):
        status, body, _ = self.client.call(
            "POST", "/api/items/181/done", {}, headers=self.qexo())
        self.assertEqual((status, body["seq"]), (201, 1))
        status, body, _ = self.client.call(
            "POST", "/api/items/181/cancel", {"note": "moot"},
            headers=self.qexo())
        self.assertEqual((status, body["seq"]), (201, 2))
        atoms = read_log(self.tmp, "resolutions.jsonl")
        self.assertEqual(
            [(a["register_number"], a["outcome"], a["user"])
             for a in atoms],
            [(181, "done", "qexo"), (181, "cancelled", "qexo")])

    def test_qexo_writes_drain_under_the_scope_owner(self):
        # The drain (scoped to will) sees the token's atoms: the
        # scope owner's drain is how write-backs reconcile.
        self.client.call("POST", "/api/entries",
                         {"text": "phone-born"}, headers=self.qexo())
        self.client.call("POST", "/api/items/181/done", {},
                         headers=self.qexo())
        status, body, _ = self.client.call(
            "GET", "/api/entries/pending?after_seq=0",
            headers={"X-Drain-Token": DRAIN})
        self.assertEqual(status, 200)
        self.assertEqual([a["user"] for a in body["atoms"]], ["qexo"])
        status, body, _ = self.client.call(
            "GET", "/api/resolutions?after_seq=0",
            headers={"X-Drain-Token": DRAIN})
        self.assertEqual(status, 200)
        self.assertEqual([a["user"] for a in body["atoms"]], ["qexo"])
        # Another login's session read does not see them.
        amy, _csrf = self.login("amy", "hunter3")
        status, body, _ = amy.call(
            "GET", "/api/resolutions?after_seq=0")
        self.assertEqual(status, 200)
        self.assertEqual(body["atoms"], [])


class TestQexoStaysInScope(ScopeOwnerCase):
    def test_qexo_cannot_close_outside_its_scope(self):
        status, body, _ = self.client.call(
            "POST", "/api/items/182/done", {}, headers=self.qexo())
        self.assertEqual((status, body["error"]),
                         (404, "unknown register number"))
        self.assertEqual(read_log(self.tmp, "resolutions.jsonl"), [])

    def test_no_scope_owner_configured_closes_nothing(self):
        app = make_app(tempfile.mkdtemp(), qexo_user=None)
        client = Client(app)
        status, _, _ = client.call(
            "POST", "/api/items/181/done", {}, headers=self.qexo())
        self.assertEqual(status, 404)

    def test_scope_is_not_widened(self):
        # No reads under the token.
        for path in ("/api/entries/pending?after_seq=0",
                     "/api/resolutions?after_seq=0"):
            status, _, _ = self.client.call(
                "GET", path, headers=self.qexo())
            self.assertEqual(status, 401)
        # No login under the token.
        status, _, headers = self.client.call(
            "POST", "/api/login",
            {"uid": "will", "password": "wrong"}, headers=self.qexo())
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)
        # The drain token still cannot write, even in scope.
        status, _, _ = self.client.call(
            "POST", "/api/items/181/done", {},
            headers={"X-Drain-Token": DRAIN})
        self.assertEqual(status, 401)


class TestSessionRuleUnchanged(ScopeOwnerCase):
    def test_owner_closes_non_owner_refused(self):
        will, csrf = self.login("will", "hunter2")
        status, _, _ = will.call(
            "POST", "/api/items/181/done", {}, csrf=csrf)
        self.assertEqual(status, 201)
        status, body, _ = will.call(
            "POST", "/api/items/182/done", {}, csrf=csrf)
        self.assertEqual((status, body["error"]),
                         (404, "unknown register number"))
        amy, csrf = self.login("amy", "hunter3")
        status, _, _ = amy.call(
            "POST", "/api/items/182/done", {}, csrf=csrf)
        self.assertEqual(status, 201)
        atoms = read_log(self.tmp, "resolutions.jsonl")
        self.assertEqual([a["user"] for a in atoms], ["will", "amy"])


class TestRefusalCausesInLog(ScopeOwnerCase):
    def test_unknown_vs_out_of_scope(self):
        # Identical to the caller...
        s1, b1, _ = self.client.call(
            "POST", "/api/items/999/done", {}, headers=self.qexo())
        s2, b2, _ = self.client.call(
            "POST", "/api/items/182/done", {}, headers=self.qexo())
        self.assertEqual((s1, b1), (s2, b2))
        self.assertEqual((s1, b1["error"]),
                         (404, "unknown register number"))
        # ...distinct in the service log.
        self.assertEqual(len(self.log_lines), 2)
        self.assertIn("999", self.log_lines[0])
        self.assertIn("unknown", self.log_lines[0])
        self.assertIn("182", self.log_lines[1])
        self.assertIn("owned by 'amy'", self.log_lines[1])
        self.assertIn("caller scope 'will'", self.log_lines[1])

    def test_session_refusals_logged_with_their_causes(self):
        will, csrf = self.login("will", "hunter2")
        will.call("POST", "/api/items/999/done", {}, csrf=csrf)
        will.call("POST", "/api/items/182/done", {}, csrf=csrf)
        self.assertEqual(len(self.log_lines), 2)
        self.assertIn("unknown", self.log_lines[0])
        self.assertIn("owned by 'amy'", self.log_lines[1])
        self.assertIn("(caller will)", self.log_lines[1])


if __name__ == "__main__":
    unittest.main()
