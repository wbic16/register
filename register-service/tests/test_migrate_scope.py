import json
import tempfile
import unittest
from pathlib import Path

from regsvc.migrate_scope import migrate


def _write_jsonl(path, atoms):
    path.write_text(
        "".join(json.dumps(a, sort_keys=True) + "\n" for a in atoms),
        encoding="utf-8")


def _read_jsonl(path):
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestMigrateScope(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        _write_jsonl(self.dir / "pending-entries.jsonl", [
            {"type": "entry", "text": "legacy, no user", "seq": 1,
             "ts": 100},
            {"type": "entry", "text": "old login", "user": "will",
             "seq": 2, "ts": 101},
            {"type": "entry", "text": "already scoped",
             "user": "wbic16", "seq": 3, "ts": 102},
        ])
        _write_jsonl(self.dir / "resolutions.jsonl", [
            {"type": "resolution", "register_number": 9,
             "user": "will", "outcome": "done", "seq": 1, "ts": 100},
        ])
        (self.dir / "credentials.json").write_text(json.dumps({
            "will": [{"credential_id": "cred-old", "public_key": "pk",
                      "sign_count": 3}],
            "wbic16": [{"credential_id": "cred-new",
                        "public_key": "pk2", "sign_count": 1}],
        }), encoding="utf-8")
        (self.dir / "sessions.json").write_text(json.dumps({
            "sid-1": {"uid": "will", "created": 1, "expires": 9999999999,
                      "csrf": "x", "reg_challenge": None},
            "sid-2": {"uid": "wbic16", "created": 1,
                      "expires": 9999999999, "csrf": "y",
                      "reg_challenge": None},
        }), encoding="utf-8")

    def test_all_atoms_scoped_losslessly(self):
        reports = migrate(self.dir, "wbic16")
        by_file = {r["file"]: r for r in reports}
        entries = by_file["pending-entries.jsonl"]
        # Counts: 3 before, 3 after; 1 already, 2 reassigned,
        # 1 of the reassigned had no user at all.
        self.assertEqual(
            (entries["total"], entries["already"],
             entries["reassigned"], entries["missing_user"]),
            (3, 1, 2, 1))
        atoms = _read_jsonl(self.dir / "pending-entries.jsonl")
        self.assertEqual(len(atoms), 3)
        self.assertTrue(all(a["user"] == "wbic16" for a in atoms))
        # Order, seq, and every other field preserved.
        self.assertEqual([a["seq"] for a in atoms], [1, 2, 3])
        self.assertEqual(atoms[0]["text"], "legacy, no user")
        self.assertEqual(atoms[1]["ts"], 101)
        res = _read_jsonl(self.dir / "resolutions.jsonl")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["user"], "wbic16")
        self.assertEqual(res[0]["register_number"], 9)
        self.assertEqual(by_file["resolutions.jsonl"]["total"], 1)

    def test_credentials_moved_and_deduped(self):
        reports = migrate(self.dir, "wbic16")
        cred_report = {r["file"]: r for r in reports}["credentials.json"]
        self.assertEqual(cred_report["moved"], 1)
        data = json.loads(
            (self.dir / "credentials.json").read_text(encoding="utf-8"))
        self.assertEqual(list(data), ["wbic16"])
        ids = [c["credential_id"] for c in data["wbic16"]]
        self.assertEqual(sorted(ids), ["cred-new", "cred-old"])

    def test_sessions_rehomed(self):
        migrate(self.dir, "wbic16")
        data = json.loads(
            (self.dir / "sessions.json").read_text(encoding="utf-8"))
        self.assertTrue(all(s["uid"] == "wbic16"
                            for s in data.values()))
        self.assertEqual(data["sid-1"]["csrf"], "x")  # fields intact

    def test_backups_kept(self):
        migrate(self.dir, "wbic16")
        for name in ("pending-entries.jsonl", "resolutions.jsonl",
                     "credentials.json", "sessions.json"):
            backup = self.dir / (name + ".pre-scope-migration")
            self.assertTrue(backup.exists(), name)

    def test_idempotent_second_run(self):
        migrate(self.dir, "wbic16")
        before = (self.dir / "pending-entries.jsonl").read_bytes()
        reports = migrate(self.dir, "wbic16")
        entries = {r["file"]: r for r in reports}[
            "pending-entries.jsonl"]
        self.assertEqual(entries["reassigned"], 0)
        self.assertEqual(entries["already"], 3)
        self.assertEqual(
            (self.dir / "pending-entries.jsonl").read_bytes(), before)

    def test_unparseable_log_aborts_untouched(self):
        bad = self.dir / "pending-entries.jsonl"
        bad.write_text("{not json\n", encoding="utf-8")
        with self.assertRaises(Exception):
            migrate(self.dir, "wbic16")
        self.assertEqual(bad.read_text(encoding="utf-8"), "{not json\n")
        self.assertFalse(
            (self.dir / "pending-entries.jsonl.pre-scope-migration")
            .exists())

    def test_missing_files_are_empty_reports(self):
        empty = Path(tempfile.mkdtemp())
        reports = migrate(empty, "wbic16")
        self.assertTrue(all(r.get("total", 0) == 0 or
                            r.get("moved", 0) == 0 for r in reports))


if __name__ == "__main__":
    unittest.main()
