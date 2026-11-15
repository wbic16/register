#!/usr/bin/env python3
"""Build jobs.phext: the house's job register.

A job is a defined piece of the house's work, stated completely
enough that someone fit to do it — a person or an agent — can take
it up from the scroll alone: what the work is, why it exists, what
done looks like, what it draws on, and its standing (open / taken /
done). jobs.phext was created at Will's direction on 2026-11-14,
with the Assay build as its first job.

Source of truth: ~/workspace/phext/jobs-source.json — a list of job
records {coordinate, title, issued, standing, body, notes, results,
nudge, coordinate_basis}. Edit the JSON, never the .phext; rebuild
after every edit, in the same session.

Each job's coordinate is computed from the job's own words (its
title and body text) by the Singular holographic merge — the same
machinery as artifacts.phext (imported from the singular skill's
task_coordinate.py, never re-implemented). On collision the scroll
component is nudged up by 1 until free and the nudge is recorded in
the source entry. A job's coordinate never changes afterwards;
notes and results append to its scroll as work proceeds.

Regenerate:  python3 ~/workspace/phext/build_jobs_phext.py
Check:       python3 ~/workspace/phext/build_jobs_phext.py --check
             (rebuilds to a temp file; prints CURRENT / DRIFT, exit 0/1)
Output:      ~/workspace/phext/jobs.phext (deterministic for a given
             source file). Conventions follow build_tasks_phext.py:
             the 9 phext delimiters, coordinates 1-indexed, implode
             walks sorted coordinates.

The Home scroll (1.1.1/1.1.1/1.1.1) is generated: it carries the
register's charter and an index of every job (coordinate — title —
standing).
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/jobs-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/jobs.phext")
HOME_COORD = "1.1.1/1.1.1/1.1.1"
STANDINGS = ("open", "taken", "done")


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


def render_job(j):
    lines = [f"# {j['title']}", ""]
    lines.append(f"Coordinate: {j['coordinate']}")
    lines.append(f"Issued: {j['issued']}")
    lines.append(f"Standing: {j['standing']}")
    lines.append("")
    lines.append(j["body"].strip())
    if j.get("notes"):
        lines.append("")
        lines.append("Notes:")
        lines += [f"- {n}" for n in j["notes"]]
    if j.get("results"):
        lines.append("")
        lines.append("Results:")
        lines += [f"- {r}" for r in j["results"]]
    lines.append("")
    return "\n".join(lines)


def render_home(jobs):
    lines = [
        "# jobs.phext — the house's job register",
        "",
        "A job is a defined piece of the house's work, stated completely",
        "enough that someone fit to do it — a person or an agent — can",
        "take it up from the scroll alone: what the work is, why it",
        "exists, what done looks like, what it draws on, and its",
        "standing.",
        "",
        "Standing is one of: open (no one has taken it), taken (someone",
        "is on it), done (the work stands complete). One scroll per job,",
        "at a coordinate computed from the job's own words by the",
        "Singular holographic merge — the job's permanent address here.",
        "Notes and results append to a job's scroll as work proceeds;",
        "a job's standing changes in its source entry, and the register",
        "is rebuilt in the same session. Source of truth:",
        "jobs-source.json beside this builder (build_jobs_phext.py);",
        "never hand-edit the .phext.",
        "",
        f"Jobs recorded: {len(jobs)}",
        "",
        "Index (coordinate — title — standing):",
    ]
    for j in sorted(jobs, key=lambda x: parse_coord(x["coordinate"])):
        lines.append(f"- {j['coordinate']} — {j['title']} — {j['standing']}")
    lines.append("")
    return "\n".join(lines)


def build():
    with open(SRC_PATH) as f:
        jobs = json.load(f)["jobs"]
    coords = [j["coordinate"] for j in jobs]
    assert len(coords) == len(set(coords)), "duplicate job coordinates"
    assert HOME_COORD not in coords, "home coordinate is generated, not a job"
    for j in jobs:
        assert j["standing"] in STANDINGS, \
            f"standing must be one of {STANDINGS}: {j['coordinate']} has {j['standing']!r}"
    scrolls = {HOME_COORD: render_home(jobs)}
    for j in jobs:
        scrolls[j["coordinate"]] = render_job(j)
    for coord, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord}: {bad}"
    return implode(scrolls), jobs


def main():
    check = "--check" in sys.argv
    blob, jobs = build()
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        if os.path.exists(OUT_PATH):
            with open(OUT_PATH, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            if current == digest:
                print(f"CURRENT: jobs.phext matches jobs-source.json (sha256 {digest})")
                return 0
        print(f"DRIFT: jobs.phext does not match jobs-source.json (rebuilt sha256 {digest})")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"jobs.phext: {len(jobs)} jobs + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
