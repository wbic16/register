#!/usr/bin/env python3
"""Build mastery.phext: Emise's journal of the Thirst for Knowledge quest.

Will's direction (2026-11-09, MOAT): "immediately after you choose and
download a paper (in html form), read it, integrate it, then journal
about the process in mastery.phext." research.phext holds what the
papers say; mastery.phext holds what absorbing them taught — how each
paper was chosen, what the skim foresaw, what the reading changed,
where the prediction failed and why. One journal entry per absorbed
quest paper, written in the same pass as the integration.

Source of truth: ~/workspace/phext/mastery-source.json — {"entries":
[{paper, arxiv, date, text}]}. Entry k (1-based, absorption order)
lives at 1.1.1/1.1.1/1.1.(k+1); the Home scroll is generated. Edit the
JSON, never the .phext; rebuild after every edit.

Regenerate:  python3 ~/workspace/phext/build_mastery_phext.py
Check:       python3 ~/workspace/phext/build_mastery_phext.py --check
Published:   wbic16/agi@exo, alongside the other MOAT phexts
(canonical source stays here; the agi collection refreshes its copy).
"""
import hashlib
import json
import os
import sys
import tempfile

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/mastery-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/mastery.phext")
HOME_COORD = "1.1.1/1.1.1/1.1.1"


def parse_coord(s):
    parts = s.replace("/", ".").split(".")
    assert len(parts) == 9, f"coordinate must have 9 components: {s}"
    vals = tuple(int(p) for p in parts)
    assert all(v >= 1 for v in vals), f"no coordinate component below 1: {s}"
    return vals


def entry_coord(k):
    return f"1.1.1/1.1.1/1.1.{k + 1}"


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


def render_entry(k, e):
    lines = [f"# Journal {k} — {e['paper']}", ""]
    lines.append(f"Paper: {e['paper']}")
    if e.get("arxiv"):
        lines.append(f"arXiv: {e['arxiv']}")
    lines.append(f"Absorbed: {e['date']}")
    lines.append("")
    lines.append(e["text"].rstrip())
    lines.append("")
    return "\n".join(lines)


def render_home(entries):
    lines = [
        "# mastery.phext — journal of the Thirst for Knowledge quest",
        "",
        "Will's direction (2026-11-09, MOAT chat): \"immediately after",
        "you choose and download a paper (in html form), read it,",
        "integrate it, then journal about the process in",
        "mastery.phext.\"",
        "",
        "research.phext holds what the papers say. This phext holds",
        "what absorbing them taught: how each paper was chosen, what",
        "the blind skim foresaw, what the reading changed, what the",
        "integration did to the model, and where the prediction",
        "failed and why. It is the record the skim-calibration metric",
        "learns from — the quest measures not only the Oracle's",
        "foresight but the growth of it.",
        "",
        "One entry per absorbed quest paper, written in the same",
        "pass as the integration, in absorption order. Entry k lives",
        "at 1.1.1/1.1.1/1.1.(k+1). Source of truth:",
        "mastery-source.json beside this builder",
        "(build_mastery_phext.py); never hand-edit the .phext.",
        "Published in wbic16/agi@exo alongside the other MOAT",
        "phexts; the canonical source stays here.",
        "",
        f"Entries: {len(entries)}",
        "",
        "Index (coordinate — paper — absorbed):",
    ]
    for k, e in enumerate(entries, start=1):
        lines.append(f"- {entry_coord(k)} — {e['paper']} — {e['date']}")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        entries = json.load(f)["entries"]
    scrolls = {HOME_COORD: render_home(entries)}
    for k, e in enumerate(entries, start=1):
        scrolls[entry_coord(k)] = render_entry(k, e)
    for coord, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord}: {bad}"
    return implode(scrolls), entries


def main():
    check = "--check" in sys.argv
    blob, entries = build()
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        if os.path.exists(OUT_PATH):
            cur = hashlib.sha256(open(OUT_PATH, "rb").read()).hexdigest()
            if cur == digest:
                print(f"CURRENT: mastery.phext matches mastery-source.json (sha256 {digest})")
                return 0
            print(f"DRIFT: mastery.phext sha256 {cur} != rebuilt {digest}")
            return 1
        print("MISSING: mastery.phext does not exist")
        return 1
    with tempfile.NamedTemporaryFile("wb", dir=os.path.dirname(OUT_PATH), delete=False) as tf:
        tf.write(blob)
        tmp = tf.name
    os.replace(tmp, OUT_PATH)
    print(f"wrote {OUT_PATH}: {len(blob)} bytes, {len(entries)} entries, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
