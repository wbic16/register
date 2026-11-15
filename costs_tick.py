#!/usr/bin/env python3
"""Log a tick on one item's meter: costs_tick.py <slug|goal_id> --tokens N --will-minutes F --note "..." """
import argparse, json, pathlib, subprocess, sys
HERE = pathlib.Path.home() / "workspace/phext"
ap = argparse.ArgumentParser()
ap.add_argument("item"); ap.add_argument("--tokens", type=int, default=0)
ap.add_argument("--will-minutes", type=float, default=0.0); ap.add_argument("--note", default="")
ap.add_argument("--date", default="2026-11-14")
a = ap.parse_args()
p = HERE / "costs-source.json"
d = json.loads(p.read_text())
for it in d["items"]:
    if a.item in (it["slug"], it["goal_id"]):
        it["tokens"] += a.tokens; it["will_minutes"] += a.will_minutes
        it["ticks"].append({"date": a.date, "tokens": a.tokens, "will_minutes": a.will_minutes, "note": a.note})
        p.write_text(json.dumps(d, indent=1, ensure_ascii=False))
        subprocess.run([sys.executable, str(HERE / "build_costs_phext.py")], check=True, capture_output=True)
        r = d["rate"]
        tt = sum(i["tokens"] for i in d["items"]); tw = sum(i["will_minutes"] for i in d["items"])
        print(f"{it['title']}: {it['tokens']:,} tokens · {it['will_minutes']:.1f} Will-min (${it['will_minutes']*r['usd_per_min']/1e9:,.1f}B)")
        print(f"FLEET: {tt:,} tokens · {tw:.1f} Will-min · ${tw*r['usd_per_min']/1e9:,.1f}B")
        break
else:
    sys.exit(f"no such item: {a.item}")
