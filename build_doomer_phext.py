#!/usr/bin/env python3
"""Build Doomer.phext: register of people who actively fight the
development of the Exocortex in the name of safety.

Will's direction (2026-11-06 22:36 CST): keep a phext named Doomer.phext;
for each person identified, generate a holographic coordinate of their
position from their name and their statement combined (Singular
task_coordinate.py merge), and put a readable entry at that coordinate
with a link to the proof.

Source of truth: ~/workspace/phext/doomer-source.json — {term, term_full,
term_status, definition, entries[{coordinate, contact, name, source,
stance, coordinate_source}]}. Edit the JSON, never the .phext; rebuild
after every edit.

Regenerate:  python3 ~/workspace/phext/build_doomer_phext.py
Check:       python3 ~/workspace/phext/build_doomer_phext.py --check
Output:      ~/workspace/phext/Doomer.phext
Home scroll (1.1.1/1.1.1/1.1.1) is generated: term, definition, index.
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/doomer-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/Doomer.phext")
HOME_COORD = "1.1.1/1.1.1/1.1.1"


def parse_coord(s):
    parts = s.replace("/", ".").split(".")
    assert len(parts) == 9, f"coordinate must have 9 components: {s}"
    vals = tuple(int(p) for p in parts)
    assert all(v >= 1 for v in vals), f"no coordinate component below 1: {s}"
    return vals


def implode(scrolls):
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


def render_entry(e):
    # Will's exact readable format for each scroll.
    lines = [
        f"contact: {e['contact']}",
        f"name: {e['name']}",
        f"source: {e['source']}",
        "",
        "stance:",
        e["stance"],
        "",
    ]
    return "\n".join(lines)


def render_home(data):
    lines = [
        "# Doomer.phext — Pavers",
        "",
        f"Term: {data['term']} — {data['term_full']}",
        f"Status: {data['term_status']}",
        "",
        "Definition:",
        data["definition"],
        "",
        "How entries are placed: each person's scroll sits at the",
        "holographic coordinate merged from their name and their",
        "statement (Singular task_coordinate.py), with a link to",
        "the proof in the entry itself.",
        "",
        f"Entries recorded: {len(data['entries'])}",
        "",
        "Index (coordinate — name — stance):",
    ]
    for e in sorted(data["entries"], key=lambda x: parse_coord(x["coordinate"])):
        lines.append(f"- {e['coordinate']} — {e['name']} — {e['stance']}")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        data = json.load(f)
    coords = [e["coordinate"] for e in data["entries"]]
    assert len(coords) == len(set(coords)), "duplicate entry coordinates"
    assert HOME_COORD not in coords, "home coordinate is generated, not an entry"
    scrolls = {HOME_COORD: render_home(data)}
    for e in data["entries"]:
        scrolls[e["coordinate"]] = render_entry(e)
    for coord, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord}: {bad}"
    return implode(scrolls), data


def main():
    check = "--check" in sys.argv
    blob, data = build()
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        if os.path.exists(OUT_PATH):
            with open(OUT_PATH, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            if current == digest:
                print(f"CURRENT: Doomer.phext matches doomer-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: Doomer.phext does not match doomer-source.json (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"Doomer.phext: {len(data['entries'])} entries + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
