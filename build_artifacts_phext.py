#!/usr/bin/env python3
"""Build artifacts.phext: the register of generated artifacts.

Will's standing order (2026-11-07 23:11 CST): "whenever you generate
an artifact like the md above, place it into artifacts.phext using a
holographic coordinate. Push it into human.git as usual." Every
artifact Emise generates is inscribed here at a coordinate computed
from the artifact's OWN words by the Singular holographic merge
(the task_coordinate.py machinery: tokenize as the Singular checker
does, average each distinct word's atlas position component-wise,
round half up, never below 1; archive-only words rest at home
1.1.1/1.1.1/1.1.1, words in neither at the far corner
9.9.9/9.9.9/9.9.9).

Source of truth: ~/workspace/phext/artifacts-source.json — a list of
artifact records {coordinate, title, source, inscribed, sha256},
where sha256 is the source file's SHA-256 at inscription. Edit the
JSON, never the .phext; rebuild after every edit. Process: the
artifact-phext-inscription skill.

Regenerate:  python3 ~/workspace/phext/build_artifacts_phext.py
Check:       python3 ~/workspace/phext/build_artifacts_phext.py --check
             (rebuilds in memory; prints CURRENT when artifacts.phext
             matches the manifest AND every source file still matches
             its inscribed sha256; STALE when a source file has changed
             since inscription; DRIFT when the .phext itself differs.
             Exit 0 only when CURRENT.)
Output:      ~/workspace/phext/artifacts.phext (deterministic for a
             given source file). Conventions follow
             build_tasks_phext.py: the 9 phext delimiters, coordinates
             1-indexed, implode walks sorted coordinates.

Each artifact's scroll is a provenance header (title, source path,
date inscribed, sha256) followed by the artifact's full text,
byte-faithful. The Home scroll (1.1.1/1.1.1/1.1.1) is generated: it
carries Will's order and an index of every inscribed artifact
(coordinate — title — source path).
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/artifacts-source.json")
OUT_PATH = os.path.expanduser("~/workspace/phext/artifacts.phext")
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


def read_source(a):
    path = os.path.expanduser(a["source"])
    with open(path, "rb") as f:
        raw = f.read()
    return raw, hashlib.sha256(raw).hexdigest()


def render_artifact(a, raw):
    text = raw.decode("utf-8")
    lines = [
        f"# {a['title']}",
        "",
        f"Title: {a['title']}",
        f"Source: {a['source']}",
        f"Inscribed: {a['inscribed']}",
        f"SHA-256: {a['sha256']}",
        "",
        "---",
        "",
    ]
    scroll = "\n".join(lines) + text
    if not scroll.endswith("\n"):
        scroll += "\n"
    return scroll


def render_home(artifacts):
    lines = [
        "# artifacts.phext — the register of generated artifacts",
        "",
        "Will's standing order (2026-11-07 23:11 CST): \"whenever you",
        "generate an artifact like the md above, place it into",
        "artifacts.phext using a holographic coordinate. Push it into",
        "human.git as usual.\"",
        "",
        "Every artifact Emise generates is inscribed here at a",
        "coordinate computed from the artifact's own words by the",
        "Singular holographic merge. Each scroll carries a provenance",
        "header (title, source path, date inscribed, SHA-256 of the",
        "source file) followed by the artifact's full text. Source of",
        "truth: artifacts-source.json beside this builder",
        "(build_artifacts_phext.py); never hand-edit the .phext.",
        "artifacts.phext is published to wbic16/human@exo.",
        "",
        f"Artifacts inscribed: {len(artifacts)}",
        "",
        "Index (coordinate — title — source):",
    ]
    for a in sorted(artifacts, key=lambda x: parse_coord(x["coordinate"])):
        lines.append(f"- {a['coordinate']} — {a['title']} — {a['source']}")
    lines.append("")
    return "\n".join(lines)


def load_manifest():
    with open(SRC_PATH) as f:
        return json.load(f)["artifacts"]


def build():
    artifacts = load_manifest()
    coords = [a["coordinate"] for a in artifacts]
    assert len(coords) == len(set(coords)), "duplicate artifact coordinates"
    assert HOME_COORD not in coords, "home coordinate is generated, not an artifact"
    scrolls = {HOME_COORD: render_home(artifacts)}
    stale = []
    for a in artifacts:
        raw, digest = read_source(a)
        if digest != a["sha256"]:
            stale.append((a, digest))
        scrolls[a["coordinate"]] = render_artifact(a, raw)
    for coord, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord}: {bad}"
    return implode(scrolls), artifacts, stale


def main():
    check = "--check" in sys.argv
    blob, artifacts, stale = build()
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        ok = os.path.exists(OUT_PATH)
        if ok:
            with open(OUT_PATH, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            ok = current == digest
        if stale:
            for a, digest_now in stale:
                print(f"STALE: {a['source']} changed since inscription "
                      f"(inscribed sha256 {a['sha256'][:16]}…, current {digest_now[:16]}…) — "
                      f"refresh the manifest entry (sha256 + inscribed date) and rebuild")
            return 1
        if ok:
            print(f"CURRENT: artifacts.phext matches artifacts-source.json and all "
                  f"{len(artifacts)} source files match their inscribed sha256 (phext sha256 {digest})")
            return 0
        print(f"DRIFT: artifacts.phext does not match artifacts-source.json (rebuilt sha256 {digest})")
        return 1
    if stale:
        for a, digest_now in stale:
            print(f"REFUSING TO BUILD: {a['source']} changed since inscription "
                  f"(inscribed sha256 {a['sha256'][:16]}…, current {digest_now[:16]}…). "
                  f"Refresh the manifest entry first.")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"artifacts.phext: {len(artifacts)} artifacts + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
