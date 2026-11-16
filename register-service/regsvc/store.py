"""Stores for the register service.

Discipline: entries and resolutions are LOG ATOMS — append-only JSONL
files, one JSON object per line, each atom stamped with a monotonically
increasing ``seq`` (its line number, starting at 1). Atoms are never
edited or deleted by the service; consumers (Emise's ticks) drain by
remembering the highest ``seq`` they have processed. Rollups (counts,
pending lists) are always computed from the atoms, never stored.

Credentials and sessions are state, not logs: small JSON documents
rewritten atomically (tmp file + fsync + os.replace).
"""

import json
import os
import threading
import time
from pathlib import Path


def _atomic_write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class JsonlLog:
    """Append-only JSONL atom log with sequence numbers."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self._seq += 1

    def append(self, atom):
        """Append one atom dict; returns the stored atom with seq+ts."""
        with self._lock:
            self._seq += 1
            stored = dict(atom)
            stored["seq"] = self._seq
            stored.setdefault("ts", int(time.time()))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(stored, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return stored

    def read_all(self, after_seq=0, user=None):
        """All atoms with seq > after_seq, in order.

        When ``user`` is given, only atoms owned by that login are
        returned (per-user scoping: an atom belongs to the uid stamped
        in its ``user`` field at append time; atoms with no ``user``
        field belong to nobody and match no scope — they become
        visible only after the scope migration assigns them an owner).
        """
        out = []
        if not self.path.exists():
            return out
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                atom = json.loads(line)
                if atom.get("seq", 0) <= after_seq:
                    continue
                if user is not None and atom.get("user") != user:
                    continue
                out.append(atom)
        return out

    @property
    def last_seq(self):
        return self._seq


class CredentialStore:
    """WebAuthn credentials keyed by LDAP uid.

    Shape: {uid: [{credential_id, public_key, sign_count, transports,
    created_ts}, ...]} — ids/keys are base64url strings.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def add(self, uid, credential):
        with self._lock:
            creds = self._data.setdefault(uid, [])
            if any(c["credential_id"] == credential["credential_id"]
                   for c in creds):
                return False
            creds.append(credential)
            _atomic_write_json(self.path, self._data)
            return True

    def list_for(self, uid):
        return list(self._data.get(uid, []))

    def find(self, uid, credential_id):
        for c in self._data.get(uid, []):
            if c["credential_id"] == credential_id:
                return c
        return None

    def update_sign_count(self, uid, credential_id, new_count):
        with self._lock:
            cred = self.find(uid, credential_id)
            if cred is None:
                return False
            cred["sign_count"] = new_count
            _atomic_write_json(self.path, self._data)
            return True


class SessionStore:
    """Server-side sessions persisted as one JSON document.

    Shape: {session_id: {uid, created, expires, csrf, reg_challenge}}
    ``reg_challenge`` is a base64url WebAuthn challenge or None.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {}
        self._purge_locked()

    def _purge_locked(self):
        now = int(time.time())
        dead = [sid for sid, s in self._data.items()
                if s.get("expires", 0) <= now]
        for sid in dead:
            del self._data[sid]
        if dead:
            _atomic_write_json(self.path, self._data)

    def create(self, session_id, record):
        with self._lock:
            self._data[session_id] = record
            _atomic_write_json(self.path, self._data)

    def get(self, session_id):
        with self._lock:
            rec = self._data.get(session_id)
            if rec is None:
                return None
            if rec.get("expires", 0) <= int(time.time()):
                del self._data[session_id]
                _atomic_write_json(self.path, self._data)
                return None
            return dict(rec)

    def update(self, session_id, **fields):
        with self._lock:
            rec = self._data.get(session_id)
            if rec is None:
                return False
            rec.update(fields)
            _atomic_write_json(self.path, self._data)
            return True

    def delete(self, session_id):
        with self._lock:
            if session_id in self._data:
                del self._data[session_id]
                _atomic_write_json(self.path, self._data)
                return True
            return False
