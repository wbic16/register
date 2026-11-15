#!/usr/bin/env python3
"""Build barnacles.phext: register of barnacle accounts.

Will's term (his tweets, Oct 2024): barnacles are follower accounts that
attach and stay — 0 posts, negative follow/follower ratio, account
younger than 1 year. He purges/blocks them.

Will's direction (2026-11-07): add the 792 accounts flagged in X list
2116659176894071283 (fetched by Grok, delivered by Will) to
barnacles.phext, with his tweets as the reference for the term.

Source of truth: ~/workspace/phext/barnacles-source.json —
{definition, criteria, references[], source_list{}, entries[{n, handle}]}.
Edit the JSON, never the .phext; rebuild after every edit.

Placement: one scroll per account, in list order, enumerated in
Volume 2 — coordinate 2.1.1/1.1.1/S.T.B where S = hundred block,
T = ten block, B = unit of the entry number. Handles are not words in
the Singular atlas (a handle alone merges to the far corner
9.9.9/9.9.9/9.9.9), so holographic merging cannot separate 792
accounts; enumeration is used instead and stated in the Home scroll.

Regenerate:  python3 ~/workspace/phext/build_barnacles_phext.py
Check:       python3 ~/workspace/phext/build_barnacles_phext.py --check
Output:      ~/workspace/phext/barnacles.phext
Home scroll (1.1.1/1.1.1/1.1.1) is generated: term, definition,
criteria, tweet references, source list, cross-reference, index.
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/barnacles-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/barnacles.phext")
HOME_COORD = "1.1.1/1.1.1/1.1.1"


def parse_coord(s):
    parts = s.replace("/", ".").split(".")
    assert len(parts) == 9, f"coordinate must have 9 components: {s}"
    vals = tuple(int(p) for p in parts)
    assert all(v >= 1 for v in vals), f"no coordinate component below 1: {s}"
    return vals


def entry_coord(n):
    """Entry n (1-indexed) -> 2.1.1/1.1.1/S.T.B (hundred/ten/unit)."""
    m = n - 1
    return f"2.1.1/1.1.1/{m // 100 + 1}.{m // 10 % 10 + 1}.{m % 10 + 1}"


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


def render_entry(e, data):
    sl = data["source_list"]
    lines = [
        f"contact: x.com/{e['handle']}",
        f"handle: @{e['handle']}",
        f"entry: {e['n']} of {len(data['entries'])}",
        f"source: X list {sl['id']} ({sl['url']}), {sl['note']}",
        "",
        "cross-reference (checked 2026-11-07):",
        "wavefront: not present (0 of 792 in wavefront.phext, 521 people)",
        "archive: not present (0 hits in Will's tweets or liked tweets, 2008-2025)",
        "",
        "status: flagged on the source list as a barnacle. The flag is",
        "the list's; the account was not individually verified against",
        "the criteria in this phext's Home scroll.",
        "",
    ]
    return "\n".join(lines)


def render_home(data):
    sl = data["source_list"]
    lines = [
        "# barnacles.phext — Barnacles",
        "",
        "Term: Barnacles — Will's own word, from his tweets (below).",
        "",
        "Definition:",
        data["definition"],
        "",
        "Criteria (Will's tweet, 2024-10-13):",
    ]
    for c in data["criteria"]:
        lines.append(f"- {c}")
    lines += [
        "",
        "References — Will's tweets:",
    ]
    for r in data["references"]:
        lines.append(f"- {r['date']} (id {r['id']}): \"{r['text']}\"")
    lines += [
        "",
        "Source of this register's entries:",
        f"X list {sl['id']} — {sl['url']}",
        sl["note"],
        f"List ID decodes to a creation time of {sl['created']}.",
        "",
        "Cross-reference (2026-11-07): none of the 792 accounts is in",
        "the wavefront (521 people), and none appears anywhere in",
        "Will's Twitter archive — not in his tweets, retweets,",
        "mentions, or the 47,973 tweets he liked.",
        "",
        "How entries are placed: one scroll per account, in list",
        "order, enumerated in Volume 2 at 2.1.1/1.1.1/S.T.B, where",
        "S = hundred block, T = ten block, B = unit of the entry",
        "number. Handles are not words in the Singular atlas (a",
        "handle alone merges to the far corner 9.9.9/9.9.9/9.9.9),",
        "so holographic merging cannot separate these accounts;",
        "enumeration is used instead.",
        "",
        f"Entries recorded: {len(data['entries'])}",
        "",
        "Index (coordinate — handle):",
    ]
    for e in data["entries"]:
        lines.append(f"- {entry_coord(e['n'])} — @{e['handle']}")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        data = json.load(f)
    ns = [e["n"] for e in data["entries"]]
    assert ns == list(range(1, len(ns) + 1)), "entries must be numbered 1..N in order"
    handles = [e["handle"].lower() for e in data["entries"]]
    assert len(handles) == len(set(handles)), "duplicate handles"
    coords = [entry_coord(n) for n in ns]
    assert len(coords) == len(set(coords)), "duplicate entry coordinates"
    assert HOME_COORD not in coords, "home coordinate is generated, not an entry"
    scrolls = {HOME_COORD: render_home(data)}
    for e in data["entries"]:
        scrolls[entry_coord(e["n"])] = render_entry(e, data)
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
                print(f"CURRENT: barnacles.phext matches barnacles-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: barnacles.phext does not match barnacles-source.json (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"barnacles.phext: {len(data['entries'])} entries + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
