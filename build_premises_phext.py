#!/usr/bin/env python3
"""Build premises.phext: the register of "Will will do X" premises.

Will's standing order (2026-11-20): "make a premises.phext and keep
track of any \"Will will do X\" items there. Specifically for things
external to us."

This register tracks plan assumptions of the form "Will will do X"
where X is EXTERNAL to us: actions only Will can take in the outside
world (his hands, his accounts, his credentials/password, his money,
his own sending). Decisions, rulings, and permissions are NOT premises
— those stay in the Waiting-on-Will register (todo.phext / register);
this register holds only the external-action subset our plans rest on.

LOCAL-ONLY: this register is never published to any repo.

Source of truth: ~/workspace/phext/premises-source.json — a list of
premise records {coordinate, statement, recorded, source, status,
crossrefs, deadline, notes}. Edit the JSON, never the .phext; rebuild
after every edit.

Regenerate:  python3 ~/workspace/phext/build_premises_phext.py
Check:       python3 ~/workspace/phext/build_premises_phext.py --check
             (rebuilds to a temp file; prints CURRENT / DRIFT, exit 0/1)
Output:      ~/workspace/phext/premises.phext (deterministic for a given
             source file). Conventions follow build_tasks_phext.py:
             the 9 phext delimiters, coordinates 1-indexed, implode
             walks sorted coordinates.

Each premise lives at a coordinate computed from its statement text by
the Singular task-coordinate tool at the moment it is recorded. The
Home scroll (1.1.1/1.1.1/1.1.1) is generated: it carries Will's order,
the external-only filter, the lifecycle, and an index of every premise
(coordinate — statement — status) with counts calculated from the
source, never hand-written.
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/premises-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/premises.phext")
HOME_COORD = "1.1.1/1.1.1/1.1.1"


def parse_coord(s):
    parts = s.replace("/", ".").split(".")
    assert len(parts) == 9, f"coordinate must have 9 components: {s}"
    vals = tuple(int(p) for p in parts)
    assert all(v >= 1 for v in vals), f"no coordinate component below 1: {s}"
    return vals


def implode(scrolls):
    """scrolls: dict coord-string -> text. Same state machine as
    build_tasks_phext.py / build_skills_phext.py."""
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


def render_premise(p):
    lines = [f"# {p['statement']}", ""]
    lines.append(f"Coordinate: {p['coordinate']}")
    lines.append(f"Statement: {p['statement']}")
    lines.append(f"Recorded: {p['recorded']}")
    lines.append(f"Source: {p['source']}")
    lines.append(f"Status: {p['status']}")
    if p.get("deadline"):
        lines.append(f"Deadline: {p['deadline']}")
    if p.get("crossrefs"):
        lines.append("")
        lines.append("Cross-references:")
        lines += [f"- {c}" for c in p["crossrefs"]]
    if p.get("notes"):
        lines.append("")
        lines.append("Notes:")
        lines += [f"- {n}" for n in p["notes"]]
    lines.append("")
    return "\n".join(lines)


def render_home(premises):
    by_status = {}
    for p in premises:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1
    counts = ", ".join(f"{n} {s}" for s, n in sorted(by_status.items()))
    lines = [
        "# premises.phext — the register of \"Will will do X\" premises",
        "",
        "Will's standing order (2026-11-20): \"make a premises.phext and",
        "keep track of any \"Will will do X\" items there. Specifically",
        "for things external to us.\"",
        "",
        "What a premise is: a plan assumption of the form \"Will will do",
        "X\" where X is EXTERNAL to us — an action only Will can take in",
        "the outside world: his hands, his accounts, his credentials or",
        "password, his money, his own sending. If a plan of ours rests on",
        "Will doing something out there, the premise is recorded here.",
        "",
        "The filter: decisions, rulings, and permissions are NOT premises",
        "and are never duplicated here — those stay in the Waiting-on-Will",
        "register. This register holds only the external-action subset.",
        "",
        "Lifecycle: open -> done / superseded. Entries are never deleted;",
        "a superseded premise stays on the record for review, with its",
        "successor named in its notes.",
        "",
        "LOCAL-ONLY: this register is not published to any repo.",
        "",
        "Generating item scheduled as task 32.6.8/9.7.11/7.6.9 per the",
        "2026-11-14 rule — this task is the tracker's first scheduled item.",
        "",
        "Source of truth: premises-source.json beside this builder",
        "(build_premises_phext.py); never hand-edit the .phext. Each",
        "premise's coordinate is computed from its statement text by the",
        "Singular task-coordinate tool when the premise is recorded.",
        "",
        f"Premises recorded: {len(premises)} ({counts})",
        "",
        "Index (coordinate — statement — status):",
    ]
    for p in sorted(premises, key=lambda x: parse_coord(x["coordinate"])):
        lines.append(f"- {p['coordinate']} — {p['statement']} — {p['status']}")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        premises = json.load(f)["premises"]
    coords = [p["coordinate"] for p in premises]
    assert len(coords) == len(set(coords)), "duplicate premise coordinates"
    assert HOME_COORD not in coords, "home coordinate is generated, not a premise"
    scrolls = {HOME_COORD: render_home(premises)}
    for p in premises:
        scrolls[p["coordinate"]] = render_premise(p)
    for coord, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord}: {bad}"
    return implode(scrolls), premises


def main():
    check = "--check" in sys.argv
    blob, premises = build()
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        if os.path.exists(OUT_PATH):
            with open(OUT_PATH, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            if current == digest:
                print(f"CURRENT: premises.phext matches premises-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: premises.phext does not match premises-source.json (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"premises.phext: {len(premises)} premises + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
