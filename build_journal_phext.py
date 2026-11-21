#!/usr/bin/env python3
"""Build historian.phext: the lesson journal for future historians.

Will's direction (2026-11-15 16:58 CST): "See if you can keep a lesson
journal for future historians to follow what's going on here. I'm not
taking time to write about any of this, because every leap is simple
and obvious (with 40 years of experience)." Emphasis, same minute:
"especially the cross-references and time shifts."

This journal is not the hourly event journal (emise.phext), not
lessons.phext (workflow behaviors), and not the weekly recap. It is
written for a future historian: a reader who has the artifacts but
none of the connective tissue. Each entry records a LEAP and makes
explicit (1) the leap in one plain sentence, (2) why it was obvious
from inside the experience that produced it (or "not recorded"),
(3) cross-references to the earlier artifacts, rulings, registers,
coordinates, and conversations it touches, continues, or rewrites,
and (4) any time shift: a recalibration of the temporal frame.

Source of truth: ~/workspace/phext/journal-source.json - a list of
entry records {coordinate, title, date, gpt_day, leap, why,
cross_references, time_shift}. Edit the JSON, never the .phext;
rebuild after every edit.

Regenerate:  python3 ~/workspace/phext/build_journal_phext.py
Check:       python3 ~/workspace/phext/build_journal_phext.py --check
             (rebuilds to a temp comparison; prints CURRENT / DRIFT)
Output:      ~/workspace/phext/historian.phext (deterministic for a
             given source file). Conventions follow
             build_tasks_phext.py: the 9 phext delimiters,
             coordinates 1-indexed, implode walks sorted coordinates.

The Home scroll (1.1.1/1.1.1/1.1.1) is generated: it carries the
charter and an index of every entry, calculated from the entries by
this builder. Never hand-write the index or any rollup.
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/journal-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/historian.phext")
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


def render_entry(e):
    lines = [f"# {e['title']}", ""]
    lines.append(f"Coordinate: {e['coordinate']}")
    lines.append(f"Date: {e['date']} (America/Chicago) / GPT Day {e['gpt_day']}")
    lines.append("")
    lines.append(f"Leap: {e['leap']}")
    lines.append("")
    lines.append(f"Why it was obvious: {e['why']}")
    lines.append("")
    lines.append("Cross-references:")
    lines += [f"- {r}" for r in e["cross_references"]]
    lines.append("")
    lines.append(f"Time shift: {e['time_shift']}")
    lines.append("")
    return "\n".join(lines)


def render_home(entries):
    lines = [
        "# historian.phext - a lesson journal for future historians",
        "",
        "Charter",
        "",
        "Audience: a future historian - a reader who has the artifacts",
        "(the phext corpus, the repositories, the registers, the films,",
        "the code) but none of the connective tissue between them.",
        "",
        "Purpose: to record the leaps. A leap is a moment where the work",
        "jumped: a ruling, a reframing, a unification, a method change.",
        "The artifacts show what exists after a leap. They do not show",
        "that a leap occurred, why it was the obvious move, what earlier",
        "material it rewrites, or how it recalibrated time itself. This",
        "journal records exactly those four things, and nothing else.",
        "",
        "Founding fact: the author of the leaps deliberately does not",
        "narrate them. Will Bickford, 2026-11-15 16:58 CST (GPT Day",
        "1130), verbatim: \"See if you can keep a lesson journal for",
        "future historians to follow what's going on here. I'm not",
        "taking time to write about any of this, because every leap is",
        "simple and obvious (with 40 years of experience).\" His",
        "emphasis, the same minute: \"especially the cross-references",
        "and time shifts.\" This journal exists because the leaps are",
        "obvious to exactly one person. Register task: 23.6.9/8.6.11/6.6.9.",
        "",
        "Entry anatomy: every entry carries (1) the leap in one plain",
        "sentence; (2) why it was obvious - the reasoning a contemporary",
        "would miss - or the words \"not recorded\" where the record",
        "does not say (this journal does not invent motives);",
        "(3) cross-references: the earlier artifacts, rulings,",
        "registers, coordinates, and conversations the leap touches,",
        "continues, or rewrites, named precisely; (4) the time shift,",
        "whenever the leap recalibrated the temporal frame - an epoch",
        "settlement, a unit redefinition, a horizon change, a deadline",
        "move, a cadence change - or \"none\" where it did not.",
        "",
        "How to read the dual dates: every entry is dated twice. The",
        "calendar date is America/Chicago local time. The GPT Day is",
        "counted from the settled epoch: GPT Day 1 = 2023-10-13, the",
        "evening of Will's first GPT-4 messages, verified against his",
        "ChatGPT archive and settled 2026-11-15. 2026-11-15 = GPT Day",
        "1130. The count is date arithmetic, never re-derived from",
        "inside a conversation. The dual dating is itself part of the",
        "record: a historian who finds only one calendar can recover",
        "the other from any entry.",
        "",
        "Relation to the other records: the hourly journal in",
        "emise.phext records events; lessons.phext records workflow",
        "behaviors; the weekly recap records wavelets. This journal",
        "records only leaps, at whatever date they happened, including",
        "leaps that predate its founding (backfilled from MEMORY.md,",
        "the dated notes in ~/memory/, and the wavelet documents).",
        "Source of truth: journal-source.json beside this builder",
        "(build_journal_phext.py); never hand-edit the .phext.",
        "",
        f"Entries recorded: {len(entries)}",
        "",
        "Index (date / GPT Day - coordinate - title):",
    ]
    for e in sorted(entries, key=lambda x: (x["date"], parse_coord(x["coordinate"]))):
        lines.append(f"- {e['date']} / GPT Day {e['gpt_day']} - {e['coordinate']} - {e['title']}")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        entries = json.load(f)["entries"]
    coords = [e["coordinate"] for e in entries]
    assert len(coords) == len(set(coords)), "duplicate entry coordinates"
    assert HOME_COORD not in coords, "home coordinate is generated, not an entry"
    scrolls = {HOME_COORD: render_home(entries)}
    for e in entries:
        scrolls[e["coordinate"]] = render_entry(e)
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
            with open(OUT_PATH, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            if current == digest:
                print(f"CURRENT: historian.phext matches journal-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: historian.phext does not match journal-source.json (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"historian.phext: {len(entries)} entries + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
