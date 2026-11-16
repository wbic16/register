"""One-time migration: assign all existing register-service data to
one login's scope (per-user scoping, 2026-11-16).

Before scoping, the service's logs were one global pile. Every atom
written by the service already carries a ``user`` field, but atoms
from before that field existed — or written under any other login —
belong to nobody's scope afterwards. This migration assigns every
existing atom to the target uid (on the live box: wbic16 — all
existing data is Will's), moves any passkey credentials stored under
other uids into the target's key, and re-homes session records the
same way.

Properties:
- Lossless: every atom's fields, order, and seq are preserved; only
  the ``user`` field is set. Counts are reported per file so the run
  is verifiable (totals before == totals after).
- Safe: a file is parsed completely before anything is written; a
  parse error aborts that file untouched. Rewrites are atomic
  (tmp + fsync + rename, original file mode preserved). A backup
  copy ``<name>.pre-scope-migration`` is kept the first time a file
  changes. Files that need no change are not touched.
- Idempotent: a second run reports zero reassignments.

Run as the service user against the live data dir while the service
is stopped:

    python3 migrate_scope.py --data-dir /var/lib/register-service \
        --uid wbic16
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

LOG_FILES = ("pending-entries.jsonl", "resolutions.jsonl")
BACKUP_SUFFIX = ".pre-scope-migration"


def _atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.chmod(tmp, path.stat().st_mode & 0o7777)
    except OSError:
        pass
    os.replace(tmp, path)


def _backup_once(path):
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def _migrate_log(path, uid):
    """Assign every atom in one JSONL log to uid. Returns a report
    dict; raises ValueError on any unparseable line (file untouched).
    """
    report = {"file": path.name, "total": 0, "already": 0,
              "reassigned": 0, "missing_user": 0, "changed": False}
    if not path.exists():
        return report
    atoms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        atom = json.loads(line)  # raises -> caller leaves file alone
        if not isinstance(atom, dict):
            raise ValueError(f"{path.name}: non-object atom line")
        atoms.append(atom)
    report["total"] = len(atoms)
    for atom in atoms:
        owner = atom.get("user")
        if owner == uid:
            report["already"] += 1
        else:
            if owner is None:
                report["missing_user"] += 1
            atom["user"] = uid
            report["reassigned"] += 1
    if report["reassigned"]:
        _backup_once(path)
        text = "".join(
            json.dumps(a, sort_keys=True) + "\n" for a in atoms)
        _atomic_write(path, text)
        report["changed"] = True
    return report


def _migrate_credentials(path, uid):
    report = {"file": path.name, "uids_before": 0, "moved": 0,
              "credentials": 0, "changed": False}
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("credentials.json: top level is not an object")
    report["uids_before"] = len(data)
    target = data.setdefault(uid, [])
    seen = {c.get("credential_id") for c in target}
    for other in [k for k in data if k != uid]:
        for cred in data.pop(other):
            if cred.get("credential_id") in seen:
                continue  # target already holds this credential
            seen.add(cred.get("credential_id"))
            target.append(cred)
            report["moved"] += 1
    report["credentials"] = len(target)
    if report["moved"]:
        _backup_once(path)
        _atomic_write(path, json.dumps(data, indent=1, sort_keys=True)
                      + "\n")
        report["changed"] = True
    return report


def _migrate_sessions(path, uid):
    report = {"file": path.name, "total": 0, "reassigned": 0,
              "changed": False}
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("sessions.json: top level is not an object")
    report["total"] = len(data)
    for rec in data.values():
        if isinstance(rec, dict) and rec.get("uid") != uid:
            rec["uid"] = uid
            report["reassigned"] += 1
    if report["reassigned"]:
        _backup_once(path)
        _atomic_write(path, json.dumps(data, indent=1, sort_keys=True)
                      + "\n")
        report["changed"] = True
    return report


def migrate(data_dir, uid):
    """Run the full migration; returns the list of per-file reports.
    Raises on the first file that cannot be parsed (that file is
    left untouched; earlier files may already be migrated — the
    migration is idempotent, so re-running after a fix is safe)."""
    data_dir = Path(data_dir)
    reports = [_migrate_log(data_dir / name, uid) for name in LOG_FILES]
    reports.append(_migrate_credentials(data_dir / "credentials.json",
                                        uid))
    reports.append(_migrate_sessions(data_dir / "sessions.json", uid))
    return reports


def _format(report):
    if "total" in report and "already" in report:
        return (f"{report['file']}: {report['total']} atoms — "
                f"{report['already']} already in scope, "
                f"{report['reassigned']} reassigned, "
                f"{report['missing_user']} had no user")
    if "moved" in report:
        return (f"{report['file']}: {report['uids_before']} uid keys — "
                f"{report['moved']} credentials moved into scope, "
                f"{report['credentials']} total in scope")
    return (f"{report['file']}: {report['total']} sessions — "
            f"{report['reassigned']} reassigned")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assign all register-service data to one login's "
                    "scope.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--uid", required=True)
    args = parser.parse_args(argv)
    try:
        reports = migrate(args.data_dir, args.uid)
    except Exception as exc:
        print(f"MIGRATION FAILED: {exc}", file=sys.stderr)
        return 1
    for report in reports:
        print(_format(report))
    print(f"migration complete: all data scoped to {args.uid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
