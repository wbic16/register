#!/usr/bin/env python3
"""Build tailscale.phext: Emise's working reference for Tailscale,
distilled from Tailscale's official documentation (tailscale.com/docs,
tailscale.com/kb) plus verified house experience on the ranch tailnet.

Source of truth: ~/workspace/phext/tailscale-source.json — a list of
{coordinate, title, body} scrolls. Edit the JSON, never the .phext;
rebuild after every edit.

Regenerate:  python3 ~/workspace/phext/build_tailscale_phext.py
Check:       python3 ~/workspace/phext/build_tailscale_phext.py --check
The Home scroll (1.1.1/1.1.1/1.1.1) is generated: purpose + index.
Conventions follow build_tasks_phext.py: the 9 phext delimiters,
coordinates 1-indexed, implode walks sorted coordinates.
"""
import hashlib
import json
import os
import sys
import tempfile

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
SRC_PATH = os.path.expanduser("~/workspace/phext/tailscale-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/tailscale.phext")
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


def build_bytes():
    src = json.load(open(SRC_PATH))
    scrolls = {}
    index = []
    for s in src["scrolls"]:
        scrolls[s["coordinate"]] = f"# {s['title']}\n\n{s['body'].rstrip()}\n"
        index.append(f"{s['coordinate']} — {s['title']}")
    home = ("# tailscale.phext — Tailscale working reference\n\n"
            "Distilled from Tailscale's official documentation plus verified\n"
            "experience on the ranch tailnet. Source of truth is\n"
            "tailscale-source.json; this file is built, never hand-edited.\n"
            "Consumed by the tailscale skill (~/workspace/custom-skills/tailscale/).\n\n"
            "Index:\n" + "\n".join(index) + "\n")
    scrolls[HOME_COORD] = home
    return implode(scrolls)


def main():
    check = "--check" in sys.argv
    data = build_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if check:
        if os.path.exists(OUT_PATH) and open(OUT_PATH, "rb").read() == data:
            print(f"CURRENT: tailscale.phext matches tailscale-source.json (sha256 {digest})")
            return 0
        print(f"DRIFT: tailscale.phext does not match (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(data)
    print(f"tailscale.phext: {len(data)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
