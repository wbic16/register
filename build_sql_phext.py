#!/usr/bin/env python3
"""Build sql.phext: the legacy-SQL knowledge phext behind the sql-legacy skill.

Started at Will's direction (2026-11-20, task 39.4.10/6.5.9/5.6.11):
"every major SQL dialect, naturally - start sql.phext". The Home scroll
is the index — every major dialect, and under each, its actions — built
for a reader who never learned SQL (Will: "the skill is for sentients
(both), a lot of people these days didn't take the time to learn SQL").

Content discipline: every claim carries provenance (will_said / post /
tested-live / emise-draft / gap). Gaps are named, never papered over
(Will: "yes, there will be many gaps"). Nothing here is scraped from the
web (Will: "test what you can, assume most of it isn't visible online").

LOCAL-ONLY for now: do not publish sql.phext anywhere without a
further word from Will.

Source of truth: ~/workspace/phext/sql-source.json — dialect records
{coordinate, name, association, actions[{name, status, note}], gaps,
notes}, page records {coordinate, title, body}, and standing bindings.
Edit the JSON, never the .phext; rebuild after every edit.

Regenerate:  python3 ~/workspace/phext/build_sql_phext.py
Check:       python3 ~/workspace/phext/build_sql_phext.py --check
             (rebuilds to a temp file; prints CURRENT / DRIFT, exit 0/1)
Output:      ~/workspace/phext/sql.phext (deterministic for a given
             source file). Conventions follow build_premises_phext.py:
             the 9 phext delimiters, coordinates 1-indexed, implode
             walks sorted coordinates.

Each dialect's coordinate was computed from its name text by the
Singular task-coordinate tool when the dialect was entered (MySQL and
PostgreSQL collided on their bare names; distinguishing words were
added — MariaDB / Postgres open source — and the collision is recorded
here so the coordinates stay explicable).
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/sql-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/sql.phext")
HOME_COORD = "1.1.1/1.1.1/1.1.1"

STEPS = [
    "Reading an action — six steps (written by Emise under Will's direction, 2026-11-20; his edits land through the interactive build):",
    "1. Name the verb. Every statement is one action wearing a costume of clauses; find the verb first.",
    "2. Say in plain words what it reads and what it changes. If you cannot say it plainly, you do not understand it yet.",
    "3. List every table it touches — directly, and through views, subqueries, and triggers. In the index, every touched table is its own token; a touch you cannot find in the index is a touch you will miss.",
    "4. Find the WHERE. That is the blast radius: the exact set of rows the action can reach.",
    "5. Ask what else fires. Triggers, cascades, defaults, and procedures that call this statement are downstream effects — the part legacy SQL hides.",
    "6. Never trust a reading you have not run. Execute the action on a copy, or inside a transaction you roll back — or, in multiversal phext, in a forked universe whose delta you read first.",
]


def parse_coord(s):
    parts = s.replace("/", ".").split(".")
    assert len(parts) == 9, f"coordinate must have 9 components: {s}"
    vals = tuple(int(p) for p in parts)
    assert all(v >= 1 for v in vals), f"no coordinate component below 1: {s}"
    return vals


def implode(scrolls):
    """scrolls: dict coord-string -> text. Same state machine as
    build_tasks_phext.py / build_premises_phext.py."""
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


def dialect_gap_count(d):
    return len(d["gaps"]) + sum(1 for a in d["actions"] if a["status"] == "gap")


def render_dialect(d):
    lines = [f"# {d['name']}", ""]
    lines.append(f"Coordinate: {d['coordinate']}")
    lines.append(d["association"])
    lines.append("")
    lines.append("Actions (status: tested = executed live and explained; gap = named, not yet knowledge):")
    for a in d["actions"]:
        lines.append(f"- {a['name']} [{a['status']}] — {a['note']}")
    lines.append("")
    lines += STEPS
    lines.append("")
    lines.append(f"Gaps in this dialect ({dialect_gap_count(d)} — a named gap beats an invented paragraph):")
    lines += [f"- {g}" for g in d["gaps"]]
    if d.get("notes"):
        lines.append("")
        lines.append("Notes:")
        lines += [f"- {n}" for n in d["notes"]]
    lines.append("")
    return "\n".join(lines)


def render_page(p):
    return f"# {p['title']}\n\nCoordinate: {p['coordinate']}\n\n{p['body']}\n"


def render_home(data):
    dialects = data["dialects"]
    pages = data["pages"]
    total_gaps = sum(dialect_gap_count(d) for d in dialects)
    lines = [
        "# sql.phext — the index",
        "",
        "Purpose (Will, 2026-11-20): \"the SQL legacy skill should help users untangle the complexity buried at the bottom of their stack.\"",
        "",
        "Success criterion (Will, 2026-11-20): \"to be successful, we need to identify why SQL is handled poorly by AI.\" The diagnosis lives on its own scroll, indexed below.",
        "",
        "Audience (Will, 2026-11-20): \"the skill is for sentients (both), a lot of people these days didn't take the time to learn SQL\" — humans who never learned SQL, and AIs. Every explanation here is written for a reader who has never seen SQL.",
        "",
        "How to navigate: start here. Pick a dialect; its scroll lists its actions (what each one does, in plain terms) and its gaps (what is not yet known, named). ANSI / standard SQL is the trunk — the tested core explanations live there; each dialect scroll owns its differences.",
        "",
        "Provenance, on every claim: will_said (Will's own words, quoted) / post (the seed exchange — Cristina's challenge and Will's acceptance; skill SOURCE.md section 1) / tested-live (executed on a real engine, logged on the verification scroll) / emise-draft (Emise's analysis, labelled, awaiting Will's ratification) / gap (named, not yet knowledge).",
        "",
        "GAP 1 — CLOSED (retrieved by live browser, 2026-11-20 07:40 CST): the seed was never a Will essay. The post Will linked is his reply accepting a challenge from Cristina A.C. (@Cristina_AC_X): point an AI at a database model and 20-year-old SQL and have it refactor the whole thing correctly. His reply, verbatim: \"ok, I'm willing to look into it. I'm currently shipping Moonshots daily. Send me your requirements!\" Her challenge is distilled on the diagnosis scroll; the exchange is recorded in the skill's SOURCE.md. The skill's origin is an accepted challenge.",
        "",
        f"Dialects indexed: {len(dialects)} — named gaps across all dialect scrolls: {total_gaps} (calculated from the source, never hand-written). Gaps are expected and welcome (Will: \"yes, there will be many gaps\") — the rest is built interactively with him.",
        "",
        "Dialect index (coordinate — dialect — actions explained / actions indexed — gaps):",
    ]
    for d in sorted(dialects, key=lambda x: parse_coord(x["coordinate"])):
        explained = sum(1 for a in d["actions"] if a["status"] == "tested")
        lines.append(f"- {d['coordinate']} — {d['name']} — {explained} / {len(d['actions'])} — {dialect_gap_count(d)}")
    foundation = next((p for p in pages if p.get("role") == "foundation"), None)
    if foundation:
        lines.append("")
        lines.append(f"START HERE — the foundation (Will, 2026-11-20: \"start with understanding how humans learn to read, analyze, and improve SQL scripts and stored procedures\"): {foundation['coordinate']} — {foundation['title']}. The human stairs — read, then analyze, then improve — come before the dialects and the diagnosis; everything else in this phext is read against them.")
    lines.append("")
    lines.append("Other scrolls:")
    for p in sorted(pages, key=lambda x: parse_coord(x["coordinate"])):
        lines.append(f"- {p['coordinate']} — {p['title']}")
    if data.get("bindings"):
        lines.append("")
        lines.append("Standing bindings:")
        lines += [f"- {b}" for b in data["bindings"]]
    lines.append("")
    lines.append("Source of truth: sql-source.json beside the builder (build_sql_phext.py); never hand-edit the .phext. LOCAL-ONLY: this phext is not published anywhere.")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        data = json.load(f)
    records = data["dialects"] + data["pages"]
    coords = [r["coordinate"] for r in records]
    assert len(coords) == len(set(coords)), "duplicate coordinates in sql-source.json"
    assert HOME_COORD not in coords, "home coordinate is generated, not a record"
    scrolls = {HOME_COORD: render_home(data)}
    for d in data["dialects"]:
        scrolls[d["coordinate"]] = render_dialect(d)
    for p in data["pages"]:
        scrolls[p["coordinate"]] = render_page(p)
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
                print(f"CURRENT: sql.phext matches sql-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: sql.phext does not match sql-source.json (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"sql.phext: {len(data['dialects'])} dialects + {len(data['pages'])} pages + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
