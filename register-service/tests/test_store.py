import time
import unittest
from pathlib import Path
import tempfile

from regsvc.store import CredentialStore, JsonlLog, SessionStore


class TestJsonlLog(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "log.jsonl"

    def test_append_assigns_monotonic_seq_and_ts(self):
        log = JsonlLog(self.path)
        a = log.append({"type": "entry", "text": "one"})
        b = log.append({"type": "entry", "text": "two"})
        self.assertEqual((a["seq"], b["seq"]), (1, 2))
        self.assertIn("ts", a)
        self.assertEqual(log.last_seq, 2)

    def test_read_all_and_after_seq(self):
        log = JsonlLog(self.path)
        for t in ["a", "b", "c"]:
            log.append({"text": t})
        self.assertEqual([a["text"] for a in log.read_all()],
                         ["a", "b", "c"])
        self.assertEqual([a["text"] for a in log.read_all(after_seq=1)],
                         ["b", "c"])
        self.assertEqual(log.read_all(after_seq=3), [])

    def test_seq_survives_reopen(self):
        log = JsonlLog(self.path)
        log.append({"text": "x"})
        log2 = JsonlLog(self.path)
        self.assertEqual(log2.append({"text": "y"})["seq"], 2)

    def test_duplicate_atoms_are_both_recorded(self):
        # Drain-time idempotency contract: the log keeps every atom,
        # including repeated "done" marks for the same register number.
        log = JsonlLog(self.path)
        atom = {"type": "resolution", "register_number": 9, "user": "will"}
        log.append(atom)
        log.append(atom)
        atoms = log.read_all()
        self.assertEqual(len(atoms), 2)
        self.assertEqual([a["register_number"] for a in atoms], [9, 9])


class TestCredentialStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "credentials.json"
        self.cred = {"credential_id": "abc", "public_key": "pk",
                     "sign_count": 0, "transports": [],
                     "created_ts": 1700000000}

    def test_add_find_list(self):
        store = CredentialStore(self.path)
        self.assertTrue(store.add("will", self.cred))
        self.assertEqual(store.find("will", "abc"), self.cred)
        self.assertEqual(len(store.list_for("will")), 1)
        self.assertIsNone(store.find("will", "nope"))
        self.assertEqual(store.list_for("nobody"), [])

    def test_add_duplicate_id_rejected(self):
        store = CredentialStore(self.path)
        store.add("will", self.cred)
        self.assertFalse(store.add("will", self.cred))
        self.assertEqual(len(store.list_for("will")), 1)

    def test_sign_count_update_persists(self):
        store = CredentialStore(self.path)
        store.add("will", self.cred)
        self.assertTrue(store.update_sign_count("will", "abc", 7))
        store2 = CredentialStore(self.path)
        self.assertEqual(store2.find("will", "abc")["sign_count"], 7)
        self.assertFalse(store.update_sign_count("will", "nope", 1))


class TestSessionStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "sessions.json"

    def test_create_get_delete(self):
        store = SessionStore(self.path)
        now = int(time.time())
        store.create("sid1", {"uid": "will", "created": now,
                              "expires": now + 100, "csrf": "tok",
                              "reg_challenge": None})
        self.assertEqual(store.get("sid1")["uid"], "will")
        self.assertTrue(store.delete("sid1"))
        self.assertIsNone(store.get("sid1"))

    def test_expired_session_is_gone(self):
        store = SessionStore(self.path)
        now = int(time.time())
        store.create("old", {"uid": "will", "created": now - 1000,
                             "expires": now - 1, "csrf": "t",
                             "reg_challenge": None})
        self.assertIsNone(store.get("old"))

    def test_update(self):
        store = SessionStore(self.path)
        now = int(time.time())
        store.create("s", {"uid": "will", "created": now,
                           "expires": now + 100, "csrf": "t",
                           "reg_challenge": None})
        self.assertTrue(store.update("s", reg_challenge="xyz"))
        self.assertEqual(store.get("s")["reg_challenge"], "xyz")
        self.assertFalse(store.update("missing", reg_challenge="x"))


if __name__ == "__main__":
    unittest.main()
