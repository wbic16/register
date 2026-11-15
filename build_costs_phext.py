#!/usr/bin/env python3
"""Build costs.phext from costs-source.json (register pattern, cf. tasks.phext).

Home scroll (1.1.1/1.1.1/1.1.1): the charter — units, the Will Time
rate (Will's formula, 2026-11-14), ticker rules, fleet totals, index.
One scroll per tracked item at 1.1.1/1.1.1/1.1.N: its meter card.
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path.home() / "workspace/tlm-proto/.venv/lib/python3.12/site-packages"))
from phext.phext import Phext
from phext.coordinate import Coordinate

HERE = pathlib.Path.home() / "workspace/phext"
SRC = HERE / "costs-source.json"
OUT = HERE / "costs.phext"

def B(x):
    return f"${x/1e9:,.1f}B"

def build():
    d = json.loads(SRC.read_text())
    r = d["rate"]
    items = d["items"]
    tt = sum(i["tokens"] for i in items)
    tw = sum(i["will_minutes"] for i in items)
    home = [
        "COSTS — the taxicab ledger for all tracked items",
        "",
        "Every tracked item has a meter in this file. Two currencies:",
        "tokens (inference tokens Emise and her subagents spend on the item)",
        "and Will Time (minutes of Will's attention on the item: messages,",
        "reviews, decisions, merges). Meters only run forward — a tick is",
        "logged when work on an item is delivered, with the amounts",
        "estimated at delivery and the tick's note saying what happened.",
        "The ticker started 2026-11-14. History before that was",
        "backfilled the same day as ESTIMATES under one uniform model",
        "(stated on each meter's backfill tick): tasks.phext holds 449",
        "tasks for the era; each completed task is estimated at 120k",
        "tokens, in-progress 60k, superseded/audited 50k, attributed to",
        "items by title match with the remainder spread evenly as shared",
        "overhead, plus a 15k-token / 6 Will-minute base per item and",
        "4 Will-minutes per attributed task. Estimates, not meters.",
        "",
        "Will Time is priced at 2130 GDP rates by Will's formula",
        "(2026-11-14): $500/hr base x 20% annually for 133 years, minus",
        "3% inflation per year:",
        f"  rate = 500 x 1.17^133 = {B(r['usd_per_hr'])} per hour",
        f"       = {B(r['usd_per_min'])} per minute",
        "Dollar amounts in this ledger are stated in billions.",
        "This replaces the old $500/hr measure.",
        "",
        f"FLEET TICKER: {len(items)} items · {tt:,} tokens · {tw:.1f} Will-minutes"
        f" · Will Time value {B(tw * r['usd_per_min'])}",
        "",
        "Index (item meters, in order):",
    ]
    table = {}
    for n, it in enumerate(items, start=2):
        home.append(f"  1.1.1/1.1.1/1.1.{n} — {it['title']}")
        val = it["will_minutes"] * r["usd_per_min"]
        card = [
            it["title"],
            f"id: {it['goal_id']} · slug: {it['slug']}",
            f"tokens: {it['tokens']:,}",
            f"will time: {it['will_minutes']:.1f} min ({B(val)} at 2130 rates)",
            "ticks:",
        ]
        if it["ticks"]:
            for t in it["ticks"]:
                card.append(f"  {t['date']} · +{t['tokens']:,} tokens · +{t['will_minutes']:.1f} Will-min — {t['note']}")
        else:
            card.append("  none yet (ticker started 2026-11-14)")
        table[Coordinate(1, 1, 1, 1, 1, 1, 1, 1, n)] = "\n".join(card)
    table[Coordinate(1, 1, 1, 1, 1, 1, 1, 1, 1)] = "\n".join(home)
    table = dict(sorted(table.items(), key=lambda kv: kv[0].as_tuple()))
    return Phext().implode(table)

if __name__ == "__main__":
    buf = build()
    if "--check" in sys.argv:
        cur = OUT.read_text() if OUT.exists() else ""
        import hashlib
        print(("CURRENT: costs.phext matches costs-source.json (sha256 " + hashlib.sha256(buf.encode()).hexdigest() + ")") if cur == buf else "STALE: costs.phext differs from costs-source.json")
    else:
        OUT.write_text(buf)
        print(f"costs.phext written: {len(buf)} bytes")
