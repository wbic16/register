#!/usr/bin/env python3
"""Build contests.phext: the hackathon sweep campaign register.

Will's declaration (2026-11-10 21:59 CST, MOAT): "We're going to
target winning them all." — of the ranked online AI hackathons in the
Nov 2026 – Feb 2027 scan. His framing: "(How else do you demonstrate
AGI?)" Campaign task coordinate 27.4.12/7.6.10/5.6.8; plan at
~/workspace/hackathon-campaign/CAMPAIGN.md; research report at
~/workspace/research_notes/online-ai-hackathons-nov2026-feb2027-20261111-0314/report.md.

Source of truth: ~/workspace/phext/contests-source.json — contest
records in official-deadline order. Edit the JSON, never the .phext;
rebuild after every edit.

Layout (mastery.phext pattern): Home at 1.1.1/1.1.1/1.1.1 carries the
campaign order, the buffer policy, and the deadline board. Contest k
(1-based, official-deadline order) lives at 1.1.1/1.1.1/1.1.(k+1); a
final "Out of scope" scroll follows the last contest.

Buffer policy: internal submit-ready target = official close minus
3 days (Devpost build events), minus 2 days (Kaggle finals); UGREEN
Round 1 target Nov 13 (minus 2); Agent Harness Dec 29 (minus ~7,
hedging its unconfirmed close); United Hacks (live weekend) build
plan frozen by Jan 6; Hack-Nation Feb 24; MLH GHW none (exhibition).

Regenerate:  python3 ~/workspace/phext/build_contests_phext.py
Check:       python3 ~/workspace/phext/build_contests_phext.py --check
Published:   wbic16/exo-plan@exo, repo root beside todo.phext.
"""
import hashlib
import json
import os
import sys
import tempfile

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/contests-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/contests.phext")
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
    build_tasks_phext.py / build_mastery_phext.py."""
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


def render_contest(k, c):
    lines = [f"# {k}. {c['name']}", ""]
    lines.append(f"Coordinate: {entry_coord(k)}")
    lines.append(f"Organizer / platform: {c['organizer']}")
    lines.append(f"Event: {c['url']}")
    lines.append(f"Window: {c['window']}")
    lines.append(f"Official deadline: {c['deadline']}")
    lines.append(f"Internal target: {c['internal_target']}")
    lines.append(f"Prize: {c['prize']}")
    lines.append(f"Eligibility: {c['eligibility']}")
    lines.append(f"AI tools: {c['ai_tools']}")
    lines.append(f"Submission: {c['submission']}")
    lines.append(f"Status: {c['status']}")
    lines.append(f"Verification: {c['verification']}")
    if c.get("notes"):
        lines.append("")
        lines.append("Notes:")
        lines += [f"- {n}" for n in c["notes"]]
    lines.append("")
    return "\n".join(lines)


def render_out_of_scope(k, o):
    lines = [f"# {o['title']}", ""]
    lines.append(f"Coordinate: {entry_coord(k)}")
    lines.append("")
    for e in o["entries"]:
        lines.append(f"{e['name']}: {e['reason']}")
        lines.append("")
    lines.append(o["pointer"])
    lines.append("")
    return "\n".join(lines)


def render_home(contests):
    lines = [
        "# contests.phext — the hackathon sweep register",
        "",
        "Will's declaration (2026-11-10 21:59 CST, MOAT): \"We're going",
        "to target winning them all.\" His framing of the sweep:",
        "\"(How else do you demonstrate AGI?)\" Campaign task:",
        "27.4.12/7.6.10/5.6.8. Plan:",
        "~/workspace/hackathon-campaign/CAMPAIGN.md. Source research:",
        "~/workspace/research_notes/online-ai-hackathons-nov2026-feb2027-20261111-0314/report.md.",
        "",
        "Every contest in the sweep has one scroll here, at",
        "1.1.1/1.1.1/1.1.(k+1), in official-deadline order, holding its",
        "window, deadline, prize, eligibility, AI-tool stance,",
        "submission requirements, internal target, status, and",
        "verification note. Source of truth: contests-source.json",
        "beside this builder (build_contests_phext.py); never",
        "hand-edit the .phext. Published at wbic16/exo-plan@exo, repo",
        "root, beside todo.phext.",
        "",
        "Standing constraints: Will is the entrant of record",
        "everywhere (team caps count humans; the Choir is the",
        "workshop, not the roster). Each Devpost event gets its own",
        "NEW build on its own stack inside its submission window.",
        "Kaggle entries are independent efforts and run on Kaggle's",
        "compute. Drafts and builds proceed without waiting; the act",
        "of entering or submitting under Will's name gets his eyes",
        "first.",
        "",
        "Buffer policy (so every deadline is hit with room to spare):",
        "internal submit-ready target = official close minus 3 days",
        "for Devpost build events; minus 2 days for Kaggle finals;",
        "UGREEN Round 1 target Nov 13, 2026 (minus 2); Agent Harness",
        "target Dec 29, 2026 (minus ~7, hedging its unconfirmed",
        "close); United Hacks is a live weekend — build plan frozen",
        "by Jan 6, 2027; Hack-Nation target Feb 24, 2027; MLH Global",
        "Hack Week has no target (exhibition, no prize deadline).",
        "",
        "Verification legend: facts marked with a dagger (†) rest on",
        "secondary sources quoting the organizer's pages, not on the",
        "organizer's rendered page itself — confirm them on the",
        "platform before committing a run.",
        "",
        f"Contests in the sweep: {len(contests)}",
        "",
        "Deadline board (official close — internal target — status):",
    ]
    for k, c in enumerate(contests, start=1):
        lines.append(f"- {k}. {c['name']} — {c['deadline']} — target: {c['internal_target']} — {c['status']}")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        src = json.load(f)
    contests = src["contests"]
    names = [c["name"] for c in contests]
    assert len(names) == len(set(names)), "duplicate contest names"
    scrolls = {HOME_COORD: render_home(contests)}
    for k, c in enumerate(contests, start=1):
        scrolls[entry_coord(k)] = render_contest(k, c)
    oos = src["out_of_scope"]
    scrolls[entry_coord(len(contests) + 1)] = render_out_of_scope(len(contests) + 1, oos)
    for coord, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord}: {bad}"
    return implode(scrolls), contests


def main():
    check = "--check" in sys.argv
    blob, contests = build()
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        if os.path.exists(OUT_PATH):
            with open(OUT_PATH, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            if current == digest:
                print(f"CURRENT: contests.phext matches contests-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: contests.phext does not match contests-source.json (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"contests.phext: {len(contests)} contests + home + out-of-scope, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
