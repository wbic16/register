#!/usr/bin/env python3
"""Build lessons.phext: every lesson Will Bickford has taught Emise, one
scroll per lesson, each at the Singular coordinate its own statement
computes to.

Regenerate:  python3 ~/workspace/phext/build_lessons_phext.py
Check:       python3 ~/workspace/phext/build_lessons_phext.py --check
             (rebuilds to a temp file, never touches the live one; prints
             CURRENT and exits 0 when lessons.phext matches the source on
             disk, DRIFT plus the drifting lesson names and exit 1 otherwise)
Output:      ~/workspace/phext/lessons.phext (deterministic for a given source)

Source of truth: ~/workspace/phext/lessons-source.phext — exactly the lesson
scrolls (statement first line, provenance, derivation note), nothing else.
The 67 scrolls were copied faithfully from the build for PR #12 (wbic16/human,
branch emise/lessons-into-incipit, commit 74c2064ad776107918815d6033e144f921bbc385),
where the same lessons were added to Incipit.phext. Future lessons are
appended to the source (at their computed coordinates) and this builder is
re-run; lessons.phext itself is never hand-edited and stays local,
unpublished, alongside skills.phext.

Conventions follow build_skills_phext.py exactly: the 9 phext delimiters
(LEVEL_BYTES, library..scroll), coordinates 1-indexed, implode walks sorted
coordinates advancing state level-by-level. The only assigned coordinate is
Home at 1.1.1/1.1.1/1.1.1; every lesson coordinate was found, not assigned —
computed from the lesson statement's exact words by the Singular holographic
merge (~/workspace/custom-skills/singular/scripts/task_coordinate.py).
"""
import hashlib
import os
import re
import sys
import tempfile

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_TO_LEVEL = {b: i for i, b in enumerate(LEVEL_BYTES)}

SOURCE_PATH = os.path.expanduser("~/workspace/phext/lessons-source.phext")
OUT_PATH = os.path.expanduser("~/workspace/phext/lessons.phext")
HOME_COORD = "1.1.1/1.1.1/1.1.1"
PR_COMMIT = "74c2064ad776107918815d6033e144f921bbc385"

PROV_RE = re.compile(r"Given (\d{4}-\d{2}-\d{2}) · Source: .*? · \[(verbatim|distilled)\]")
INDEX_RE = re.compile(
    r"^(\S+)  (.*)  (\d{4}-\d{2}-\d{2})  \[(verbatim|distilled)\]  (\d+) bytes  sha256:([0-9a-f]{64})$")


def c(s):
    return tuple(int(x) for part in s.split("/") for x in part.split("."))


def fmt(coord):
    return "%d.%d.%d/%d.%d.%d/%d.%d.%d" % coord


def parse_bytes(data):
    """Dead-reckoning parse of raw phext bytes -> {coord_str: raw_bytes} for
    non-empty scrolls. Same walk as parse_phext.py, at the byte level."""
    coord = [1] * 9
    scrolls = {}
    buf = bytearray()
    current = fmt(tuple(coord))
    for b in data:
        lvl = DELIM_TO_LEVEL.get(b)
        if lvl is None:
            buf.append(b)
        else:
            if bytes(buf).strip():
                if current in scrolls:
                    sys.exit(f"FAIL: duplicate coordinate {current} in source")
                scrolls[current] = bytes(buf)
            buf = bytearray()
            coord[lvl] += 1
            for j in range(lvl + 1, 9):
                coord[j] = 1
            current = fmt(tuple(coord))
    if bytes(buf).strip():
        if current in scrolls:
            sys.exit(f"FAIL: duplicate coordinate {current} in source")
        scrolls[current] = bytes(buf)
    return scrolls


def implode(scrolls):
    """scrolls: dict coord-string -> bytes. Same state machine as build_skills_phext.py."""
    items = sorted(((c(k), v) for k, v in scrolls.items()))
    out = bytearray()
    state = [1] * 9
    for target, text in items:
        for lvl in range(9):
            while state[lvl] < target[lvl]:
                out.append(LEVEL_BYTES[lvl])
                state[lvl] += 1
                for j in range(lvl + 1, 9):
                    state[j] = 1
        assert tuple(state) == target, (state, target)
        out += text
    return bytes(out)


def lesson_meta(coord_s, raw):
    """(short statement, date given, mark) from one lesson scroll.
    Fails loudly if the scroll does not carry its provenance."""
    text = raw.decode("utf-8")  # raises unless valid UTF-8
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        sys.exit(f"FAIL: empty lesson scroll at {coord_s}")
    m = PROV_RE.search(text)
    if not m:
        sys.exit(f"FAIL: lesson at {coord_s} lacks its provenance line (Given <date> · Source: … · [mark])")
    return lines[0].strip(), m.group(1), m.group(2)


def build():
    """Build the phext blob from lessons-source.phext.
    Returns (blob, entries); entries is a list of
    (coord_str, short, date, mark, data_bytes) ordered by coordinate."""
    if not os.path.exists(SOURCE_PATH):
        sys.exit(f"FAIL: source not found: {SOURCE_PATH}")
    source_raw = open(SOURCE_PATH, "rb").read()
    source_sha = hashlib.sha256(source_raw).hexdigest()
    lessons = parse_bytes(source_raw)
    if not lessons:
        sys.exit("FAIL: source holds no lesson scrolls")
    if HOME_COORD in lessons:
        sys.exit(f"FAIL: a lesson sits at {HOME_COORD}, which is reserved for Home")

    entries = []
    for coord_s in sorted(lessons, key=c):
        raw = lessons[coord_s]
        short, date, mark = lesson_meta(coord_s, raw)
        entries.append((coord_s, short, date, mark, raw))

    n_verbatim = sum(1 for e in entries if e[3] == "verbatim")
    n_distilled = len(entries) - n_verbatim

    index_lines = []
    for coord_s, short, date, mark, raw in entries:
        sha = hashlib.sha256(raw).hexdigest()
        index_lines.append(f"{coord_s}  {short}  {date}  [{mark}]  {len(raw)} bytes  sha256:{sha}")

    home = f"""Home — lessons.phext: the lessons Will Bickford has taught Emise, each at its own coordinate
kind: observed | origin: Muse (this agent) | built by: ~/workspace/phext/build_lessons_phext.py
source of truth: ~/workspace/phext/lessons-source.phext (sha256 {source_sha}) — regenerate
the phext by re-running the builder; never hand-edit this file. Nothing here is published
by the builder; lessons.phext stays local, alongside skills.phext.

What this is: a standalone curation of every lesson Will has given Emise — standing
orders, rulings, and corrections. The {len(entries)} lesson scrolls are copied faithfully from
the build for PR #12 (wbic16/human, branch emise/lessons-into-incipit, commit
{PR_COMMIT}, 2026-11-06), where the same lessons were added to Incipit.phext.
Curation copies; it does not re-derive or re-word. Each lesson scroll holds the
statement as its first line, the lesson in full, its provenance (date given, source,
[verbatim] or [distilled]), and its derivation note.

Placement: Home alone is assigned, at {HOME_COORD}. Every lesson coordinate was
found, not assigned — computed from the lesson statement's exact words by the
Singular holographic merge (task_coordinate.py over the Singular atlas): tokenize
the statement as the Singular checker does; take each distinct word's holographic
position (the average of every CYOA scroll holding the word; a word in Will's
archive but not CYOA rests at home 1.1.1/1.1.1/1.1.1; a word in neither rests at
the far corner 9.9.9/9.9.9/9.9.9); average component-wise across the distinct
words, round half up, never below 1. Coordinates are internal to this phext.

Counts: {len(entries)} lessons — {n_verbatim} [verbatim], {n_distilled} [distilled].

Index (coordinate  lesson  given  mark  size  SHA-256 of the scroll), ordered by coordinate:
{HOME_COORD}  (this scroll)  Home — the map
{chr(10).join(index_lines)}
Scrolls: {len(entries) + 1}
"""

    scrolls = {HOME_COORD: home.encode("utf-8")}
    for coord_s, _, _, _, raw in entries:
        scrolls[coord_s] = raw

    blob = implode(scrolls)
    return blob, entries


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def committed_index():
    """Parse the per-lesson index out of the committed lessons.phext Home scroll.
    Returns {coord: (short, date, mark, sha256)} or None if unavailable."""
    try:
        raw = open(OUT_PATH, "rb").read()
    except OSError:
        return None
    end = next((i for i, b in enumerate(raw) if b in DELIM_TO_LEVEL), len(raw))
    try:
        home = raw[:end].decode("utf-8")
    except UnicodeDecodeError:
        return None
    idx = {}
    for line in home.splitlines():
        m = INDEX_RE.match(line)
        if m:
            idx[m.group(1)] = (m.group(2), m.group(3), m.group(4), m.group(6))
    return idx or None


def check():
    """Rebuild to a temp file and compare SHA-256 with the committed
    lessons.phext. Prints CURRENT (exit 0) or DRIFT with the drifting lesson
    names (exit 1). Never modifies the live lessons.phext."""
    blob, entries = build()
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT_PATH),
                               prefix=".lessons-check-", suffix=".phext")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        rebuilt_sha = sha256_file(tmp)
    finally:
        os.unlink(tmp)
    if not os.path.exists(OUT_PATH):
        print(f"DRIFT: {OUT_PATH} does not exist (rebuilt sha256 {rebuilt_sha})")
        return 1
    current_sha = sha256_file(OUT_PATH)
    if current_sha == rebuilt_sha:
        print(f"CURRENT: lessons.phext matches the source on disk (sha256 {current_sha})")
        return 0
    print("DRIFT: lessons.phext is stale")
    print(f"  committed: sha256 {current_sha}")
    print(f"  rebuilt:   sha256 {rebuilt_sha}")
    old = committed_index()
    new = {coord: (short, date, mark, hashlib.sha256(raw).hexdigest())
           for coord, short, date, mark, raw in entries}
    if old is None:
        print("  (could not parse the committed Home index to name the drift)")
    else:
        changed, added, removed = [], [], []
        for coord in sorted(set(old) | set(new)):
            if coord not in old:
                added.append(new[coord])
            elif coord not in new:
                removed.append(old[coord])
            elif old[coord] != new[coord]:
                changed.append(new[coord])
        named = False
        for label, group in (("changed", changed), ("new", added), ("removed", removed)):
            if group:
                named = True
                print(f"  {label}: {len(group)} lesson(s)")
                for short, _, _, _ in sorted(group):
                    print(f"    - {short}")
        if not named:
            print("  (per-lesson index identical — drift is in Home metadata)")
    print("  fix: python3 ~/workspace/phext/build_lessons_phext.py  (rebuild), then --check again")
    return 1


def main():
    if "--check" in sys.argv[1:]:
        sys.exit(check())
    blob, entries = build()
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"wrote {OUT_PATH}: {len(blob)} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    print(f"scrolls: {len(entries) + 1} (1 Home + {len(entries)} lessons)")
    if entries:
        print(f"  coordinate span: {entries[0][0]} .. {entries[-1][0]}")


if __name__ == "__main__":
    main()
