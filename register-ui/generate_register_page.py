#!/usr/bin/env python3
"""Generate the Waiting-on-Will register web page (register.phext.io).

Source of record: the markdown register (default
~/workspace/your_files/waiting-on-will.md). Item numbers, titles, and
waiting-since dates are parsed from the markdown and cross-checked
against its own header count. The todo.phext mirror source
(~/workspace/phext/todo-source.json, integration.register_items) only
enriches each row with the curated one-line action and its
good-singularity tier; if the mirror lacks an item, the register's own
prose is used as the action text.

Output: one self-contained HTML file (inline CSS/JS, no frameworks),
open items sorted OLDEST first (anti-recency), with a search box.

Usage:
    generate_register_page.py [--register PATH] [--mirror PATH]
                              [--out PATH]

Refresh flow: re-run this script, then copy the generated index.html
to /sites/web/register.phext.io/ on awsbox.
"""

import argparse
import html
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")

ITEM_START = re.compile(r"^(\d+)\.\s+\*\*", re.M)
SINCE_MARKER_RE = re.compile(r"\*Since\s+(\d{4}-\d{2}-\d{2})")
SINCE_RE = re.compile(r"[Ss]ince\s+(\d{4}-\d{2}-\d{2})")
HEADER_COUNT_RE = re.compile(r"\*\*(\d+) active items\*\*")
HISTORY_START = re.compile(r"^\*Resolved ", re.M)


def clean_md(text):
    """Strip light markdown: links -> text, backticks/bold markers out."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").replace("**", "").replace("*", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_register(text):
    """Parse numbered items out of the register markdown.

    The active list ends where the history begins (the first
    '*Resolved ' entry). Item titles may wrap across lines, so items
    are chunked by start position and the title is taken between the
    first pair of '**' markers in the chunk.
    """
    header = HEADER_COUNT_RE.search(text)
    header_count = int(header.group(1)) if header else None
    hist = HISTORY_START.search(text)
    active = text[:hist.start()] if hist else text
    starts = list(ITEM_START.finditer(active))
    items = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(active)
        chunk = active[m.start():end]
        rest = chunk[m.end() - m.start():]
        close = rest.find("**")
        if close >= 0:
            title_raw, body_raw = rest[:close], rest[close + 2:]
        else:
            title_raw, body_raw = rest, ""
        body_raw = body_raw.lstrip(": ").strip()
        title = clean_md(title_raw)
        body = clean_md(body_raw)
        # Prefer the explicit '*Since YYYY-MM-DD*' marker; fall back to
        # any 'since <date>' phrasing in the cleaned text (line wraps
        # and lowercase variants occur in the register).
        sm = SINCE_MARKER_RE.search(chunk) or SINCE_RE.search(f"{title} {body}")
        items.append({
            "n": int(m.group(1)),
            "title": title,
            "body": body,
            "since": sm.group(1) if sm else None,
        })
    return header_count, items


def fallback_action(item):
    """Action text from the register prose when the mirror has none."""
    body = item["body"]
    body = re.sub(r"[Ss]ince\s+\d{4}-\d{2}-\d{2}[^.]*\.?", "", body).strip()
    body = re.sub(r"\[(task|goal)[^\]]*\]\s*$", "", body).strip()
    if len(body) > 700:
        body = body[:700].rsplit(" ", 1)[0] + " …"
    return body


def linkify(escaped_text):
    """Wrap bare URLs in anchors (input is already HTML-escaped)."""
    def repl(m):
        url = m.group(0)
        trail = ""
        while url and url[-1] in ".,);":
            trail = url[-1] + trail
            url = url[:-1]
        return f'<a href="{url}" rel="noopener">{url}</a>{trail}'
    return re.sub(r"https?://[^\s<]+", repl, escaped_text)


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Waiting on Will — Register</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         margin: 0; padding: 24px 20px 48px; line-height: 1.45; }
  main { max-width: 1180px; margin: 0 auto; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .meta { color: #888; font-size: 13px; margin-bottom: 16px; }
  .meta b { color: inherit; }
  #q { width: 100%; box-sizing: border-box; padding: 9px 12px; font-size: 15px;
       border: 1px solid #9996; border-radius: 8px; margin-bottom: 14px; }
  #quick { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
       margin-bottom: 12px; }
  #qe { flex: 1 1 340px; box-sizing: border-box; padding: 9px 12px;
       font-size: 15px; border: 1px solid #4a7dbb; border-radius: 8px; }
  #quick button { padding: 9px 14px; font-size: 14px; border: 1px solid #9998;
       border-radius: 8px; background: transparent; color: inherit; cursor: pointer; }
  #qe-note { color: #888; font-size: 12px; }
  tr.pending td { background: #4a7dbb14; }
  tr.pending .rm { cursor: pointer; color: #c0392b; font-weight: 700; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { text-align: left; vertical-align: top; padding: 8px 10px;
           border-bottom: 1px solid #9994; }
  th { position: sticky; top: 0; background: Canvas; font-size: 12px;
       text-transform: uppercase; letter-spacing: .04em; color: #888; }
  td.num { font-variant-numeric: tabular-nums; white-space: nowrap; font-weight: 600; }
  td.title { font-weight: 600; min-width: 180px; }
  td.since, td.age { white-space: nowrap; font-variant-numeric: tabular-nums; }
  td.age.old { color: #c0392b; font-weight: 700; }
  td.age.mid { color: #b9770e; font-weight: 600; }
  .tier { display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 6px;
          border: 1px solid #9998; border-radius: 20px; white-space: nowrap; }
  a { color: #4a7dbb; }
  footer { margin-top: 20px; color: #888; font-size: 12px; }
  #none { display: none; padding: 18px 0; color: #888; }
</style>
</head>
<body>
<main>
  <h1>⏳ Waiting on Will — the register</h1>
  <div class="meta"><b>$count open items</b> · oldest first · generated $generated
  · source: waiting-on-will.md (register of record) · register read-only, quick-entry drafts are browser-local</div>
  <div id="quick">
    <input id="qe" type="text" placeholder="Quick entry — type a new wait item, Enter drops it on top of the pile…" autocomplete="off">
    <button id="qe-add" type="button">Add to pile</button>
    <button id="qe-copy" type="button">Copy pending lines</button>
    <span id="qe-note">Drafts stay in this browser until Emise numbers them into the register.</span>
  </div>
  <input id="q" type="search" placeholder="Filter items… (number, word, tier)" autocomplete="off">
  <table id="grid">
    <thead><tr><th>#</th><th>Item</th><th>Action needed</th><th>Tier</th>
    <th>Waiting since</th><th>Age</th></tr></thead>
    <tbody>
$rows
    </tbody>
  </table>
  <div id="none">No items match the filter.</div>
  <footer>Register numbers are permanent and monotonic. An item leaves this
  page only when Will acts on it. Regenerate: generate_register_page.py
  (wbic16/register) → deploy index.html to register.phext.io.</footer>
</main>
<script>
  const q = document.getElementById('q');
  const none = document.getElementById('none');
  q.addEventListener('input', () => {
    const needle = q.value.trim().toLowerCase();
    let visible = 0;
    for (const r of document.querySelectorAll('#grid tbody tr')) {
      const hit = !needle || r.textContent.toLowerCase().includes(needle);
      r.style.display = hit ? '' : 'none';
      if (hit) visible++;
    }
    none.style.display = visible ? 'none' : 'block';
  });
  q.focus();

  // Quick entry: drafts land on top of the pile, persist in this browser
  // (localStorage), and leave only when Emise numbers them into the
  // register of record. "Copy pending lines" hands them over in one paste.
  const QE_KEY = 'register-quick-entries';
  const tbody = document.querySelector('#grid tbody');
  const qe = document.getElementById('qe');
  const loadQE = () => { try { return JSON.parse(localStorage.getItem(QE_KEY)) || []; } catch { return []; } };
  const saveQE = list => localStorage.setItem(QE_KEY, JSON.stringify(list));
  function renderQE() {
    tbody.querySelectorAll('tr.pending').forEach(r => r.remove());
    const list = loadQE();
    for (let i = list.length - 1; i >= 0; i--) {
      const tr = document.createElement('tr');
      tr.className = 'pending';
      const today = new Date().toISOString().slice(0, 10);
      tr.innerHTML = '<td class="num">new</td><td class="title"></td>' +
        '<td class="action">pending — not numbered yet</td><td>draft</td>' +
        '<td class="since">' + today + '</td>' +
        '<td class="age"><span class="rm" title="Remove draft">✕</span></td>';
      tr.querySelector('.title').textContent = list[i];
      tr.querySelector('.rm').addEventListener('click', () => {
        const l = loadQE(); l.splice(i, 1); saveQE(l); renderQE();
      });
      tbody.prepend(tr);
    }
  }
  function addQE() {
    const text = qe.value.trim();
    if (!text) return;
    const list = loadQE(); list.push(text); saveQE(list);
    qe.value = ''; renderQE(); qe.focus();
  }
  document.getElementById('qe-add').addEventListener('click', addQE);
  qe.addEventListener('keydown', e => { if (e.key === 'Enter') addQE(); });
  document.getElementById('qe-copy').addEventListener('click', async () => {
    const list = loadQE();
    if (!list.length) return;
    const lines = list.map(t => '- Quick entry (unnumbered): ' + t).join('\n');
    try { await navigator.clipboard.writeText(lines); } catch { qe.value = lines; qe.select(); }
  });
  renderQE();
</script>
</body>
</html>
"""

ROW = """      <tr><td class="num">{n}</td><td class="title">{title}</td>
      <td class="action">{action}</td><td>{tier}</td>
      <td class="since">{since}</td><td class="age {age_class}">{age}</td></tr>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default=str(
        Path.home() / "workspace/your_files/waiting-on-will.md"))
    ap.add_argument("--mirror", default=str(
        Path.home() / "workspace/phext/todo-source.json"))
    ap.add_argument("--out", default="index.html")
    args = ap.parse_args()

    text = Path(args.register).read_text(encoding="utf-8")
    header_count, items = parse_register(text)

    mirror = {}
    mpath = Path(args.mirror)
    if mpath.exists():
        try:
            reg_items = json.loads(mpath.read_text(encoding="utf-8")) \
                ["integration"]["register_items"]
            mirror = {int(e["n"]): e for e in reg_items}
        except Exception as exc:  # mirror is enrichment only; never fatal
            print(f"warning: mirror unusable ({exc}); prose fallback",
                  file=sys.stderr)

    if header_count is not None and header_count != len(items):
        print(f"warning: header says {header_count} active items, "
              f"parsed {len(items)}", file=sys.stderr)
    if mirror and len(mirror) != len(items):
        print(f"warning: mirror holds {len(mirror)} items, "
              f"register parsed {len(items)}", file=sys.stderr)

    now = datetime.now(TZ)
    today = now.date()
    rows = []
    enriched = sorted(
        items,
        key=lambda it: (it["since"] or "9999-12-31", it["n"]))
    for it in enriched:
        entry = mirror.get(it["n"], {})
        action = entry.get("action") or fallback_action(it)
        tier = entry.get("tier") or ""
        since = it["since"] or entry.get("since") or ""
        if since:
            age_days = (today - date.fromisoformat(since)).days
            age = f"{age_days}d"
            age_class = "old" if age_days >= 30 else ("mid" if age_days >= 14 else "")
        else:
            age, age_class = "—", ""
        rows.append(ROW.format(
            n=it["n"],
            title=html.escape(it["title"]),
            action=linkify(html.escape(action)),
            tier=(f'<span class="tier">{html.escape(tier)}</span>' if tier else ""),
            since=html.escape(since) or "—",
            age=age, age_class=age_class))

    generated = now.strftime("%a %Y-%m-%d %H:%M %Z")
    from string import Template
    page = Template(PAGE).substitute(count=len(items), generated=generated,
                                     rows="\n".join(rows))
    Path(args.out).write_text(page, encoding="utf-8")
    print(f"wrote {args.out}: {len(items)} items "
          f"(header count {header_count}, mirror {len(mirror)}), "
          f"generated {generated}")


if __name__ == "__main__":
    main()
