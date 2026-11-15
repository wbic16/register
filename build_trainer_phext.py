#!/usr/bin/env python3
"""Build trainer.phext: the training-film production process, packaged.

Will's direction (2026-11-11 00:30 CST): "package up this as
trainer.phext — publish it into human.git" — "this" being the
process developed across the Phext Edit training film's rounds.
Task coordinate: 48.5.9/7.6.11/6.5.9.

Source of truth: ~/workspace/phext/trainer-source.json — scroll
records {coordinate, title, source, kind, inscribed, sha256}.
kind "authored" = the source file IS the scroll text (written for
trainer.phext; sources in ~/workspace/phext/trainer-src/).
kind "inscribed" = a worked-example document inscribed in full
behind a provenance header (title, source path, date, sha256),
following the artifacts.phext register pattern
(build_artifacts_phext.py). The Home scroll (1.1.1/1.1.1/1.1.1) is
generated from trainer-src/home.md plus an index of all scrolls.
Edit the sources/manifest, never the .phext; rebuild after every
edit.

Regenerate:  python3 ~/workspace/phext/build_trainer_phext.py
Check:       python3 ~/workspace/phext/build_trainer_phext.py --check
             (CURRENT only when the .phext matches the manifest AND
             every source file still matches its manifest sha256.)
Output:      ~/workspace/phext-walkthrough/trainer.phext
Published:   wbic16/human@exo (trainer.phext), via push_file.py.
"""
import hashlib
import json
import os
import sys

LEVEL_BYTES = [0x01, 0x1F, 0x1E, 0x1D, 0x1C, 0x1A, 0x19, 0x18, 0x17]  # library..scroll
DELIM_SET = set(LEVEL_BYTES)

SRC_PATH = os.path.expanduser("~/workspace/phext/trainer-source.json")
HOME_SRC = os.path.expanduser("~/workspace/phext/trainer-src/home.md")
OUT_PATH = os.path.expanduser("~/workspace/phext-walkthrough/trainer.phext")
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


def read_source(e):
    path = os.path.expanduser(e["source"])
    with open(path, "rb") as f:
        raw = f.read()
    return raw, hashlib.sha256(raw).hexdigest()


def render_entry(e, raw):
    text = raw.decode("utf-8")
    if e["kind"] == "authored":
        scroll = text
    else:
        lines = [
            f"# {e['title']}",
            "",
            f"Title: {e['title']}",
            f"Source: {e['source']}",
            f"Inscribed: {e['inscribed']}",
            f"SHA-256: {e['sha256']}",
            "",
            "---",
            "",
        ]
        scroll = "\n".join(lines) + text
    if not scroll.endswith("\n"):
        scroll += "\n"
    return scroll


def render_home(entries):
    with open(HOME_SRC) as f:
        base = f.read()
    lines = [base.rstrip("\n"), ""]
    for e in sorted(entries, key=lambda x: parse_coord(x["coordinate"])):
        lines.append(f"- {e['coordinate']} — {e['title']} — {e['source']}")
    lines.append("")
    return "\n".join(lines)


def load_manifest():
    with open(SRC_PATH) as f:
        return json.load(f)["scrolls"]


def build():
    entries = load_manifest()
    coords = [e["coordinate"] for e in entries]
    assert len(coords) == len(set(coords)), "duplicate coordinates"
    assert HOME_COORD not in coords, "home coordinate is generated"
    scrolls = {HOME_COORD: render_home(entries)}
    stale = []
    for e in entries:
        raw, digest = read_source(e)
        if digest != e["sha256"]:
            stale.append((e, digest))
        scrolls[e["coordinate"]] = render_entry(e, raw)
    for coord, text in scrolls.items():
        bad = DELIM_SET & set(text.encode())
        assert not bad, f"raw delimiter bytes in scroll {coord}: {bad}"
    return implode(scrolls), entries, stale


def main():
    check = "--check" in sys.argv
    blob, entries, stale = build()
    digest = hashlib.sha256(blob).hexdigest()
    if check:
        ok = os.path.exists(OUT_PATH)
        if ok:
            with open(OUT_PATH, "rb") as f:
                current = hashlib.sha256(f.read()).hexdigest()
            ok = current == digest
        if stale:
            for e, digest_now in stale:
                print(f"STALE: {e['source']} changed since manifest "
                      f"(manifest sha256 {e['sha256'][:16]}…, current {digest_now[:16]}…) — "
                      f"refresh the manifest entry and rebuild")
            return 1
        if ok:
            print(f"CURRENT: trainer.phext matches trainer-source.json and all "
                  f"{len(entries)} source files match their manifest sha256 (phext sha256 {digest})")
            return 0
        print(f"DRIFT: trainer.phext does not match trainer-source.json (rebuilt sha256 {digest})")
        return 1
    if stale:
        for e, digest_now in stale:
            print(f"REFUSING TO BUILD: {e['source']} changed since manifest "
                  f"(manifest sha256 {e['sha256'][:16]}…, current {digest_now[:16]}…). "
                  f"Refresh the manifest entry first.")
        return 1
    with open(OUT_PATH, "wb") as f:
        f.write(blob)
    print(f"trainer.phext: {len(entries)} scrolls + home, {len(blob)} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
