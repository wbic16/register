#!/usr/bin/env python3
"""Build accounting.phext from accounting-source.json (register pattern).

Will's rule (2026-11-15): never summarize what you can log+calculate.
The source holds ATOMS only:
  sessions[]  — one entry per work session (date, gpt_day, tokens,
                will_minutes, title, note), logged as work is delivered.
  git_days[]  — one entry per calendar day, extracted from git history
                (phext/code/other line adds+dels, commits, repos,
                Will's active hours + span from his commit timestamps).
  lag[]       — one entry per timed delivery (date, task, t0, t1,
                seconds, tags, source), bagged+tagged from the MTTD
                ledger (~/workspace/operation-salvage/mttd.md). t1 is
                null where the ledger states seconds without a T1.
  git_baseline[] — one entry per period of the git-history baseline
                extraction (label, start, end, partial flag, phext/code/
                other adds+dels, commits, Will's commits, repos touched,
                Will's active hours + span). The extraction reported
                WEEKLY aggregates only, so the atoms are per-week; no
                daily split is fabricated. Nets are never stored —
                the builder calculates them from adds and dels.
Every scroll beyond the atoms is CALCULATED by this builder:
  Home    1.1.1/1.1.1/1.1.1          charter + calculated standing + index
  Session 1.1.1/2.1.1/1.1.N          one scroll per session atom, in order
  Daily   1.1.1/3.<month>.<day>/1.1.1  calculated from that day's atoms
  Weekly  1.1.1/4.1.<week>/1.1.1     calculated from the week's 7 days
  Lag     1.1.1/5.1.1/1.1.N          one scroll per lag atom, in order
  GitBase 1.1.1/6.1.1/1.1.N          one scroll per git baseline atom
  GitWeek 1.1.1/6.2.<week>/1.1.1     calculated from that week's baseline atoms
  GitSum  1.1.1/6.3.1/1.1.1          calculated baseline totals + full-week averages
Weeks run Sunday-Saturday (America/Chicago); week 1 = Sun 2023-10-08 -
Sat 2023-10-14, the week containing GPT Day 1 (2023-10-13).
"""
import json, pathlib, sys, datetime
sys.path.insert(0, str(pathlib.Path.home() / "workspace/tlm-proto/.venv/lib/python3.12/site-packages"))
from phext.phext import Phext
from phext.coordinate import Coordinate

HERE = pathlib.Path.home() / "workspace/phext"
SRC = HERE / "accounting-source.json"
OUT = HERE / "accounting.phext"
EPOCH = datetime.date(2023, 10, 13)          # GPT Day 1
WEEK1_SUNDAY = datetime.date(2023, 10, 8)    # Sunday of week 1

def gpt_day(d):
    return (d - EPOCH).days + 1

def week_of(d):
    sunday = d - datetime.timedelta(days=(d.weekday() + 1) % 7)
    return (sunday - WEEK1_SUNDAY).days // 7 + 1, sunday

def net(a, d):
    return a - d

def build():
    src = json.loads(SRC.read_text())
    meta = src["meta"]
    sessions = src.get("sessions", [])
    git_days = {g["date"]: g for g in src.get("git_days", [])}
    lag = src.get("lag", [])
    baseline = src.get("git_baseline", [])
    notes = src.get("notes", [])

    sess_by_date = {}
    for s in sessions:
        sess_by_date.setdefault(s["date"], []).append(s)

    lag_by_date = {}
    for a in lag:
        lag_by_date.setdefault(a["date"], []).append(a)

    dates = sorted(set(git_days) | set(sess_by_date) | set(lag_by_date))
    weeks = {}
    for ds in dates:
        d = datetime.date.fromisoformat(ds)
        w, sunday = week_of(d)
        weeks.setdefault(w, (sunday, []))[1].append(ds)

    def lag_line(atoms):
        if not atoms:
            return "lag: 0 timed deliveries"
        mean = sum(a["seconds"] for a in atoms) / len(atoms)
        return f"lag: {len(atoms)} timed deliveries · mean {mean:.1f} s (MTTD, calculated)"

    def day_lines(ds):
        g = git_days.get(ds, {})
        ss = sess_by_date.get(ds, [])
        d = datetime.date.fromisoformat(ds)
        w, _ = week_of(d)
        out = [
            f"{ds} — GPT Day {gpt_day(d)} — week {w}",
            f"lines of phext: +{g.get('phext_add', 0):,} -{g.get('phext_del', 0):,} (net {net(g.get('phext_add', 0), g.get('phext_del', 0)):+,})",
            f"lines of code: +{g.get('code_add', 0):,} -{g.get('code_del', 0):,} (net {net(g.get('code_add', 0), g.get('code_del', 0)):+,})",
            f"other lines: +{g.get('other_add', 0):,} -{g.get('other_del', 0):,} (net {net(g.get('other_add', 0), g.get('other_del', 0)):+,})",
            f"commits: {g.get('commits', 0)} across {g.get('repos', 0)} repos",
            f"Will active hours: {g.get('will_active_hours', 0)} (span {g.get('will_span_hours', 0)})",
            f"sessions: {len(ss)} · tokens: {sum(s.get('tokens', 0) for s in ss):,} · Will-minutes: {sum(s.get('will_minutes', 0) for s in ss):.1f}",
            lag_line(lag_by_date.get(ds, [])),
        ]
        return "\n".join(out)

    def week_lines(w, sunday, dss):
        gs = [git_days.get(ds, {}) for ds in dss]
        ss = [s for ds in dss for s in sess_by_date.get(ds, [])]
        la = [a for ds in dss for a in lag_by_date.get(ds, [])]
        sat = sunday + datetime.timedelta(days=6)
        def tot(k):
            return sum(g.get(k, 0) for g in gs)
        out = [
            f"Week {w} — {sunday.isoformat()} to {sat.isoformat()} — GPT Days {gpt_day(sunday)}-{gpt_day(sat)}",
            f"lines of phext: +{tot('phext_add'):,} -{tot('phext_del'):,} (net {net(tot('phext_add'), tot('phext_del')):+,})",
            f"lines of code: +{tot('code_add'):,} -{tot('code_del'):,} (net {net(tot('code_add'), tot('code_del')):+,})",
            f"other lines: +{tot('other_add'):,} -{tot('other_del'):,} (net {net(tot('other_add'), tot('other_del')):+,})",
            f"commits: {tot('commits')} across {max([g.get('repos', 0) for g in gs] + [0])} repos (peak day)",
            f"Will active hours: {tot('will_active_hours')} (span {tot('will_span_hours')})",
            f"sessions: {len(ss)} · tokens: {sum(s.get('tokens', 0) for s in ss):,} · Will-minutes: {sum(s.get('will_minutes', 0) for s in ss):.1f}",
            lag_line(la),
            f"days with atoms: {len(dss)} of 7",
        ]
        return "\n".join(out)

    table = {}
    # Sessions — Collection 2
    for n, s in enumerate(sessions, start=1):
        body = [
            s["title"],
            f"date: {s['date']} · GPT Day {s.get('gpt_day', '')}",
            f"tokens: {s.get('tokens', 0):,} · Will-minutes: {s.get('will_minutes', 0):.1f}",
            s.get("note", ""),
        ]
        table[Coordinate(1, 1, 1, 2, 1, 1, 1, 1, n)] = "\n".join(body)
    # Daily rollups — Collection 3, Volume=month, Book=day
    for ds in dates:
        d = datetime.date.fromisoformat(ds)
        table[Coordinate(1, 1, 1, 3, d.month, d.day, 1, 1, 1)] = day_lines(ds)
    # Weekly rollups — Collection 4, Book=week number
    for w in sorted(weeks):
        sunday, dss = weeks[w]
        table[Coordinate(1, 1, 1, 4, 1, w, 1, 1, 1)] = week_lines(w, sunday, sorted(dss))
    # Lag atoms — Collection 5
    for n, a in enumerate(lag, start=1):
        body = [
            a["task"],
            f"date: {a['date']} · source: {a.get('source', '')}",
            f"T0: {a['t0']}",
            f"T1: {a['t1'] if a.get('t1') else 'not stated in ledger'}",
            f"seconds: {a['seconds']}",
            f"tags: {', '.join(a.get('tags', []))}",
        ]
        table[Coordinate(1, 1, 1, 5, 1, 1, 1, 1, n)] = "\n".join(body)

    # Git baseline — Collection 6. Atoms as extracted (per-week periods;
    # the extraction reported weekly aggregates only, so no daily split
    # is fabricated). Weekly rollups and the summary are CALCULATED.
    def rhu(x):
        return int(x + 0.5) if x >= 0 else -int(-x + 0.5)

    full_base = [a for a in baseline if not a.get("partial")]

    def avgf(k):
        return sum(a.get(k, 0) for a in full_base) / len(full_base) if full_base else 0

    for n, a in enumerate(baseline, start=1):
        w, _ = week_of(datetime.date.fromisoformat(a["start"]))
        body = [
            f"Git baseline — {a['label']}",
            f"period: {a['start']} to {a['end']} · accounting week {w}" + (" · partial week (3 days)" if a.get("partial") else " · full week (Sun-Sat)"),
            "granularity: per-week atom — source extraction reported weekly aggregates only; no daily split fabricated",
            f"lines of phext: +{a['phext_add']:,} -{a['phext_del']:,} (net {net(a['phext_add'], a['phext_del']):+,})",
            f"lines of code: +{a['code_add']:,} -{a['code_del']:,} (net {net(a['code_add'], a['code_del']):+,})",
            f"other lines: +{a['other_add']:,} -{a['other_del']:,} (net {net(a['other_add'], a['other_del']):+,})",
            f"commits: {a['commits']} (Will: {a.get('will_commits', 0)})",
            f"repos touched: {a['repos']} — {', '.join(a.get('repo_names', []))}",
            f"Will active hours: {a['will_active_hours']} (commit-touched) · span {a['will_span_hours']} hours",
            f"binary files in diffs: {a.get('binary_files', 0)}",
            f"source: {a.get('source', '')}",
        ]
        table[Coordinate(1, 1, 1, 6, 1, 1, 1, 1, n)] = "\n".join(body)

    base_by_week = {}
    for a in baseline:
        w, _ = week_of(datetime.date.fromisoformat(a["start"]))
        base_by_week.setdefault(w, []).append(a)
    for w in sorted(base_by_week):
        aa = base_by_week[w]
        def btot(k, aa=aa):
            return sum(a.get(k, 0) for a in aa)
        names = sorted({nm for a in aa for nm in a.get("repo_names", [])})
        body = [
            f"Git baseline — week {w} rollup (calculated from {len(aa)} atom(s))",
            f"period covered: {min(a['start'] for a in aa)} to {max(a['end'] for a in aa)}",
            f"lines of phext: +{btot('phext_add'):,} -{btot('phext_del'):,} (net {net(btot('phext_add'), btot('phext_del')):+,})",
            f"lines of code: +{btot('code_add'):,} -{btot('code_del'):,} (net {net(btot('code_add'), btot('code_del')):+,})",
            f"other lines: +{btot('other_add'):,} -{btot('other_del'):,} (net {net(btot('other_add'), btot('other_del')):+,})",
            f"commits: {btot('commits')} (Will: {btot('will_commits')})",
            f"repos touched: {len(names)} (union across the week's atoms)",
            f"Will active hours: {btot('will_active_hours')} (commit-touched) · span {btot('will_span_hours')} hours",
        ]
        table[Coordinate(1, 1, 1, 6, 2, w, 1, 1, 1)] = "\n".join(body)

    if baseline:
        def t_all(k):
            return sum(a.get(k, 0) for a in baseline)
        body = [
            "Git baseline — summary (calculated from atoms)",
            f"window: {baseline[0]['start']} to {baseline[-1]['end']} · atoms: {len(baseline)} ({len(full_base)} full weeks + {len(baseline) - len(full_base)} partial)",
            "granularity: per-week atoms — source extraction reported weekly aggregates only; no daily split fabricated",
            f"totals, all periods: phext +{t_all('phext_add'):,} -{t_all('phext_del'):,} (net {net(t_all('phext_add'), t_all('phext_del')):+,}) · code +{t_all('code_add'):,} -{t_all('code_del'):,} (net {net(t_all('code_add'), t_all('code_del')):+,}) · other +{t_all('other_add'):,} -{t_all('other_del'):,} (net {net(t_all('other_add'), t_all('other_del')):+,})",
            f"totals, all periods: commits {t_all('commits')} (Will: {t_all('will_commits')}) · Will active hours {t_all('will_active_hours')} (commit-touched)",
            f"full-week averages (W1-W4, per week): lines of phext added {rhu(avgf('phext_add')):,} · net {rhu(avgf('phext_add') - avgf('phext_del')):+,}",
            f"full-week averages (W1-W4, per week): lines of code added {rhu(avgf('code_add')):,} · net {rhu(avgf('code_add') - avgf('code_del')):+,}",
            f"full-week averages (W1-W4, per week): commits {rhu(avgf('commits'))} · Will active hours {avgf('will_active_hours'):.1f}",
        ]
        table[Coordinate(1, 1, 1, 6, 3, 1, 1, 1, 1)] = "\n".join(body)

    # Home — charter + calculated standing + index
    all_g = list(git_days.values())
    home = [
        meta["title"],
        "",
        meta["principle"],
        meta["epoch"],
        meta["week_rule"],
        meta["floor"],
        "costs.phext remains the per-goal meter priced in Will Time; this",
        "book is the productivity roll-up: sessions logged as atoms,",
        "git history extracted per day, every rollup calculated.",
        "",
        "Address map:",
        "  1.1.1/1.1.1/1.1.1 — this scroll",
        "  1.1.1/2.1.1/1.1.N — session atoms, in order logged",
        "  1.1.1/3.<month>.<day>/1.1.1 — daily rollups (calculated)",
        "  1.1.1/4.1.<week>/1.1.1 — weekly rollups (calculated)",
        "  1.1.1/5.1.1/1.1.N — lag atoms (MTTD), in order logged",
        "  1.1.1/6.1.1/1.1.N — git baseline atoms (per-week periods)",
        "  1.1.1/6.2.<week>/1.1.1 — git baseline weekly rollups (calculated)",
        "  1.1.1/6.3.1/1.1.1 — git baseline summary (calculated)",
        "",
        "Calculated standing (from atoms on file):",
        f"  session atoms: {len(sessions)} · tokens annotated: {sum(s.get('tokens', 0) for s in sessions):,}",
        f"  git days on file: {len(all_g)} · lines of code net: {sum(net(g.get('code_add', 0), g.get('code_del', 0)) for g in all_g):+,} · lines of phext net: {sum(net(g.get('phext_add', 0), g.get('phext_del', 0)) for g in all_g):+,}",
        f"  weeks with rollups: {len(weeks)}",
        f"  git baseline atoms: {len(baseline)} per-week periods ({baseline[0]['start']} to {baseline[-1]['end']}) · full-week averages: phext net {rhu(avgf('phext_add') - avgf('phext_del')):+,} · code net {rhu(avgf('code_add') - avgf('code_del')):+,} · commits {rhu(avgf('commits'))} · Will active hours {avgf('will_active_hours'):.1f}" if baseline else "  git baseline atoms: 0",
        f"  lag atoms: {len(lag)} · overall mean {(sum(a['seconds'] for a in lag) / len(lag)):.1f} s (MTTD, calculated)" if lag else "  lag atoms: 0",
        "",
        "Notes:",
    ]
    for nt in notes:
        home.append(f"  {nt['date']} — {nt['note']}")
    table[Coordinate(1, 1, 1, 1, 1, 1, 1, 1, 1)] = "\n".join(home)

    table = dict(sorted(table.items(), key=lambda kv: kv[0].as_tuple()))
    return Phext().implode(table)

if __name__ == "__main__":
    buf = build()
    if "--check" in sys.argv:
        cur = OUT.read_text() if OUT.exists() else ""
        import hashlib
        print(("CURRENT: accounting.phext matches accounting-source.json (sha256 " + hashlib.sha256(buf.encode()).hexdigest() + ")") if cur == buf else "STALE: accounting.phext differs from accounting-source.json")
    else:
        OUT.write_text(buf)
        print(f"accounting.phext written: {len(buf)} bytes")
