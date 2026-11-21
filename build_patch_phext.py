#!/usr/bin/env python3
"""Build patch.phext: Will's patch register.

Will's standing order (2026-11-06 18:22 CST): "for every task I issue,
record it in patch.phext, keep notes and results in the coordinate
generated initially." Every task Will issues gets a reference coordinate
from the Singular task-coordinate tool (see the task-register skill);
that coordinate is the task's scroll address in this phext, and all
notes and results for the task accumulate in that scroll.

Source of truth: ~/workspace/phext/patch-source.json — a list of task
records {coordinate, title, issued, request, verbatim, status, notes,
results}. Edit the JSON, never the .phext; rebuild after every edit.

Regenerate:  python3 ~/workspace/phext/build_patch_phext.py
Check:       python3 ~/workspace/phext/build_patch_phext.py --check
             (rebuilds to a temp file; prints CURRENT / DRIFT, exit 0/1)
Output:      ~/workspace/phext/patch.phext (deterministic for a given
             source file). Conventions follow build_skills_phext.py:
             the 9 phext delimiters, coordinates 1-indexed, implode
             walks sorted coordinates.

The Home scroll (1.1.1/1.1.1/1.1.1) is generated: it carries Will's
order and an index of every task (coordinate — title — status).
"""
import hashlib
import json
import os
import sys
import tempfile

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/patch-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/patch.phext")
HOME_COORD = "1.1.1/1.1.1/1.1.1"


def parse_coord(s):
    parts = s.replace("/", ".").split(".")
    assert len(parts) == 9, f"coordinate must have 9 components: {s}"
    vals = tuple(int(p) for p in parts)
    assert all(v >= 1 for v in vals), f"no coordinate component below 1: {s}"
    return vals


def implode(scrolls):
    """scrolls: dict coord-string -> text. Same state machine as
    build_skills_phext.py / build_exocortex.py."""
    items = sorted(((parse_coord(k), v) for k, v in scrolls.items()))
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
        out += text.encode()
    return bytes(out)


def render_patch(t):
    lines = [f"# {t['title']}", ""]
    lines.append(f"Coordinate: {t['coordinate']}")
    lines.append(f"Date: {t['date']}")
    lines.append(f"Where: {t['where']}")
    lines.append(f"Patched: {t['patched']}")
    lines.append(f"Why not the proper fix at the time: {t['why_not_proper']}")
    lines.append(f"The proper fix: {t['proper_fix']}")
    lines.append(f"Status: {t['status']}")
    if t.get("related"):
        lines.append(f"Related: {t['related']}")
    lines.append("")
    return "\n".join(lines)


def render_home(tasks):
    lines = [
        "# patch.phext \u2014 the patch register",
        "",
        "Will's standing rule (2026-11-19 22:12 CST): \"never just patch",
        "around things that can be properly fixed - if you do patch...",
        "keep a record in patch.phext so we can review and improve it",
        "later.\"",
        "",
        "Every patch applied instead of a proper fix is recorded here at",
        "the time it is applied: what was patched, why the proper fix",
        "was not done then, what the proper fix is, and its status.",
        "Superseded patches stay on the record for review. Source of",
        "truth: patch-source.json beside this builder",
        "(build_patch_phext.py); never hand-edit the .phext.",
        "",
        f"Patches recorded: {len(tasks)}",
        "",
        "Index (coordinate \u2014 title \u2014 status):",
    ]
    for t in sorted(tasks, key=lambda x: parse_coord(x["coordinate"])):
        lines.append(f"- {t['coordinate']} \u2014 {t['title']} \u2014 {t['status']}")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        tasks = json.load(f)["patches"]
    coords = [t["coordinate"] for t in tasks]
    assert len(coords) == len(set(coords)), "duplicate patch coordinates"
    assert HOME_COORD not in coords, "home coordinate is generated, not a task"
    scrolls = {HOME_COORD: render_home(tasks)}
    for t in tasks:
        scrolls[t["coordinate"]] = render_patch(t)
    for coord, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord}: {bad}"
    return implode(scrolls), tasks


def main():
    check = "--check" in sys.argv
    blob, tasks = build()
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        if os.path.exists(OUT_PATH):
            with open(OUT_PATH, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            if current == digest:
                print(f"CURRENT: patch.phext matches patch-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: patch.phext does not match patch-source.json (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"patch.phext: {len(tasks)} patches + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
