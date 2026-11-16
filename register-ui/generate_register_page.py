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
  #authbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
       margin-bottom: 10px; }
  #authbar input { padding: 8px 10px; font-size: 14px;
       border: 1px solid #9996; border-radius: 8px; }
  #authbar button, .done-btn { padding: 7px 12px; font-size: 13px;
       border: 1px solid #9998; border-radius: 8px; background: transparent;
       color: inherit; cursor: pointer; }
  #auth-note { color: #888; font-size: 12px; }
  #auth-err, #qe-err { color: #c0392b; font-size: 13px; font-weight: 600; }
  #qe-err { display: none; margin-bottom: 10px; }
  #done-dialog { border: 1px solid #9998; border-radius: 10px;
       padding: 18px; width: min(480px, calc(100% - 48px));
       background: Canvas; color: inherit; }
  #done-dialog::backdrop { background: rgba(0, 0, 0, .45); }
  #done-dialog h2 { font-size: 16px; margin: 0 0 6px; }
  #done-dialog .dlg-title { font-weight: 600; margin-bottom: 10px; }
  #done-note { width: 100%; box-sizing: border-box; min-height: 84px;
       padding: 9px 12px; font-size: 14px; border: 1px solid #9996;
       border-radius: 8px; background: transparent; color: inherit; }
  #done-err { color: #c0392b; font-size: 13px; font-weight: 600;
       min-height: 18px; margin-top: 8px; }
  #done-dialog .dlg-btns { display: flex; gap: 8px;
       justify-content: flex-end; margin-top: 10px; }
  #done-dialog .dlg-btns button { padding: 7px 12px; font-size: 13px;
       border: 1px solid #9998; border-radius: 8px; background: transparent;
       color: inherit; cursor: pointer; }
  tr.done-pending td { opacity: .55; text-decoration: line-through; }
  tr.done-pending td.done-cell { opacity: 1; text-decoration: none; }
  .done-note { font-size: 12px; color: #888; }
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
  · source: waiting-on-will.md (register of record) · entries &amp; done-marks queue via the register service; Emise numbers/closes them into the register</div>
  <div id="authbar">
    <span id="auth-out">
      <input id="au-uid" type="text" placeholder="LDAP user (e.g. will)" autocomplete="username">
      <input id="au-pw" type="password" placeholder="LDAP password" autocomplete="current-password">
      <button id="au-login" type="button">Log in</button>
      <button id="au-passkey" type="button">Use a passkey</button>
      <span id="auth-note">Log in to add to the pile or mark items done.</span>
    </span>
    <span id="auth-in" style="display:none">
      Logged in as <b id="auth-user"></b>
      <button id="au-enroll" type="button">Add a passkey</button>
      <button id="au-logout" type="button">Log out</button>
    </span>
    <span id="auth-err"></span>
  </div>
  <div id="quick">
    <input id="qe" type="text" placeholder="Quick entry — type a new wait item, Enter drops it on top of the pile…" autocomplete="off">
    <button id="qe-add" type="button">Add to pile</button>
    <span id="qe-note">Entries land in the register service queue (log in first); Emise numbers them into the register.</span>
  </div>
  <div id="qe-err"></div>
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
  (wbic16/register) → deploy index.html + register-numbers.json to register.phext.io.</footer>
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

  // ---- Register service (v2): auth, quick entry, Done buttons ----
  // The page is static; all state lives in the service at /api/.
  // Logged out: read-only grid, exactly as v1. Logged in: quick entry
  // POSTs to the service queue, and each row grows a Done button whose
  // mark lands in the service's resolutions log. Emise drains both.
  const tbody = document.querySelector('#grid tbody');
  const qe = document.getElementById('qe');
  const qeErr = document.getElementById('qe-err');
  const authErr = document.getElementById('auth-err');
  let csrfToken = null;
  let currentUser = null;

  function showErr(msg) { qeErr.textContent = msg; qeErr.style.display = 'block'; }
  function clearErr() { qeErr.textContent = ''; qeErr.style.display = 'none'; }
  function showAuthErr(msg) { authErr.textContent = msg; }
  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function api(method, path, bodyObj, useCsrf) {
    const opts = { method: method, headers: {}, credentials: 'same-origin' };
    if (bodyObj !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(bodyObj);
    }
    if (useCsrf && csrfToken) opts.headers['X-CSRF-Token'] = csrfToken;
    let status = 0, data = null, text = '';
    try {
      const r = await fetch(path, opts);
      status = r.status;
      text = await r.text();
      try { data = JSON.parse(text); } catch (e) { data = null; }
    } catch (e) {
      return { status: 0, data: null, text: '' };
    }
    return { status: status, data: data, text: text };
  }

  // -- base64url helpers for WebAuthn ceremonies --
  function b64urlToBuf(s) {
    s = s.replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    const bin = atob(s);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }
  function bufToB64url(buf) {
    const bytes = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=/g, '');
  }
  function credToJSON(cred) {
    const resp = {
      clientDataJSON: bufToB64url(cred.response.clientDataJSON)
    };
    if (cred.response.attestationObject)
      resp.attestationObject = bufToB64url(cred.response.attestationObject);
    if (cred.response.authenticatorData)
      resp.authenticatorData = bufToB64url(cred.response.authenticatorData);
    if (cred.response.signature)
      resp.signature = bufToB64url(cred.response.signature);
    resp.userHandle = cred.response.userHandle
      ? bufToB64url(cred.response.userHandle) : null;
    if (cred.response.getTransports)
      resp.transports = cred.response.getTransports();
    return {
      id: cred.id,
      rawId: bufToB64url(cred.rawId),
      type: cred.type,
      authenticatorAttachment: cred.authenticatorAttachment || null,
      clientExtensionResults: cred.getClientExtensionResults
        ? cred.getClientExtensionResults() : {},
      response: resp
    };
  }
  function decodeOptions(text, isCreate) {
    const o = JSON.parse(text);
    const pub = isCreate ? o : o;
    pub.challenge = b64urlToBuf(pub.challenge);
    if (isCreate) {
      pub.user.id = b64urlToBuf(pub.user.id);
      if (pub.excludeCredentials)
        pub.excludeCredentials.forEach(c => { c.id = b64urlToBuf(c.id); });
    } else if (pub.allowCredentials) {
      pub.allowCredentials.forEach(c => { c.id = b64urlToBuf(c.id); });
    }
    return o;
  }

  // -- auth state --
  function renderAuth() {
    const out = document.getElementById('auth-out');
    const inn = document.getElementById('auth-in');
    if (currentUser) {
      out.style.display = 'none';
      inn.style.display = '';
      document.getElementById('auth-user').textContent = currentUser;
    } else {
      out.style.display = '';
      inn.style.display = 'none';
    }
  }

  async function refreshSession() {
    const res = await api('GET', '/api/session');
    if (res.status === 200 && res.data && res.data.user) {
      currentUser = res.data.user;
      csrfToken = res.data.csrf;
    } else {
      currentUser = null;
      csrfToken = null;
    }
    renderAuth();
    if (currentUser) {
      injectDoneButtons();
      loadPending();
      loadResolutions();
    }
  }

  async function doLogin() {
    showAuthErr('');
    const uid = document.getElementById('au-uid').value.trim();
    const pw = document.getElementById('au-pw').value;
    if (!uid || !pw) { showAuthErr('Enter user and password.'); return; }
    const res = await api('POST', '/api/login', { uid: uid, password: pw });
    document.getElementById('au-pw').value = '';
    if (res.status === 200 && res.data) {
      currentUser = res.data.user;
      csrfToken = res.data.csrf;
      renderAuth();
      injectDoneButtons();
      loadPending();
      loadResolutions();
    } else if (res.status === 401) {
      showAuthErr('Invalid credentials.');
    } else if (res.status === 503) {
      showAuthErr('Directory unavailable — try again later.');
    } else {
      showAuthErr('Login failed (' + res.status + ').');
    }
  }

  async function doPasskeyLogin() {
    showAuthErr('');
    const uid = document.getElementById('au-uid').value.trim();
    if (!uid) { showAuthErr('Enter your user name first.'); return; }
    if (!window.PublicKeyCredential) {
      showAuthErr('This browser has no passkey support.'); return;
    }
    const res = await api('POST', '/api/webauthn/login/options', { uid: uid });
    if (res.status === 404) { showAuthErr('No passkeys enrolled for that user.'); return; }
    if (res.status !== 200) { showAuthErr('Passkey login failed to start.'); return; }
    let cred;
    try {
      cred = await navigator.credentials.get(
        { publicKey: decodeOptions(res.text, false) });
    } catch (e) { showAuthErr('Passkey ceremony failed: ' + (e.name || 'Error') + (e.message ? ' — ' + e.message : '')); return; }
    const verify = await api('POST', '/api/webauthn/login/verify',
      { credential: credToJSON(cred) });
    if (verify.status === 200 && verify.data) {
      currentUser = verify.data.user;
      csrfToken = verify.data.csrf;
      renderAuth();
      injectDoneButtons();
      loadPending();
      loadResolutions();
    } else {
      showAuthErr('Passkey verification failed.');
    }
  }

  async function doEnroll() {
    showAuthErr('');
    if (!window.PublicKeyCredential) {
      showAuthErr('This browser has no passkey support.'); return;
    }
    const res = await api('POST', '/api/webauthn/register/options', {}, true);
    if (res.status !== 200) { showAuthErr('Could not start passkey enrollment.'); return; }
    let cred;
    try {
      cred = await navigator.credentials.create(
        { publicKey: decodeOptions(res.text, true) });
    } catch (e) { showAuthErr('Passkey ceremony failed: ' + (e.name || 'Error') + (e.message ? ' — ' + e.message : '')); return; }
    const verify = await api('POST', '/api/webauthn/register/verify',
      { credential: credToJSON(cred) }, true);
    if (verify.status === 201) {
      showAuthErr('Passkey added.');
    } else {
      showAuthErr('Passkey enrollment failed.');
    }
  }

  async function doLogout() {
    await api('POST', '/api/logout', {}, true);
    currentUser = null;
    csrfToken = null;
    renderAuth();
    removeDoneButtons();
    tbody.querySelectorAll('tr.pending').forEach(r => r.remove());
  }

  document.getElementById('au-login').addEventListener('click', doLogin);
  document.getElementById('au-pw').addEventListener('keydown',
    e => { if (e.key === 'Enter') doLogin(); });
  document.getElementById('au-passkey').addEventListener('click', doPasskeyLogin);
  document.getElementById('au-enroll').addEventListener('click', doEnroll);
  document.getElementById('au-logout').addEventListener('click', doLogout);

  // -- quick entry: POSTs to the service queue --
  async function addQE() {
    clearErr();
    const text = qe.value.trim();
    if (!text) return;
    if (!currentUser) { showErr('Log in first — entries go to the service queue now, not this browser.'); return; }
    const res = await api('POST', '/api/entries', { text: text }, true);
    if (res.status === 201) {
      qe.value = '';
      loadPending();
      qe.focus();
    } else if (res.status === 401) {
      showErr('Session expired — log in again.');
      refreshSession();
    } else {
      showErr('Add failed (' + res.status + ') — the entry was NOT queued. Text kept above.');
    }
  }
  document.getElementById('qe-add').addEventListener('click', addQE);
  qe.addEventListener('keydown', e => { if (e.key === 'Enter') addQE(); });

  async function loadPending() {
    const res = await api('GET', '/api/entries/pending');
    if (res.status !== 200 || !res.data) return;
    tbody.querySelectorAll('tr.pending').forEach(r => r.remove());
    const atoms = res.data.atoms.slice().sort((a, b) => a.seq - b.seq);
    for (const a of atoms) {
      const tr = document.createElement('tr');
      tr.className = 'pending';
      const day = new Date(a.ts * 1000).toISOString().slice(0, 10);
      tr.innerHTML = '<td class="num">new</td><td class="title"></td>' +
        '<td class="action">pending — awaiting Emise’s numbering</td>' +
        '<td>queue</td><td class="since">' + day + '</td>' +
        '<td class="age">' + esc(a.user || '') + '</td>';
      tr.querySelector('.title').textContent = a.text;
      tbody.prepend(tr);
    }
  }

  // -- Done buttons (authenticated only; injected, never in static HTML) --
  function injectDoneButtons() {
    if (document.getElementById('done-th')) return;
    const headRow = document.querySelector('#grid thead tr');
    const th = document.createElement('th');
    th.id = 'done-th';
    th.textContent = 'Done?';
    headRow.appendChild(th);
    document.querySelectorAll('#grid tbody tr[data-n]').forEach(tr => {
      const td = document.createElement('td');
      td.className = 'done-cell';
      const n = tr.getAttribute('data-n');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'done-btn';
      btn.textContent = 'Done';
      btn.addEventListener('click', () => onDoneClick(tr, td, n));
      td.appendChild(btn);
      tr.appendChild(td);
    });
  }

  function removeDoneButtons() {
    const th = document.getElementById('done-th');
    if (th) th.remove();
    document.querySelectorAll('#grid tbody td.done-cell').forEach(td => td.remove());
    document.querySelectorAll('#grid tbody tr.done-pending')
      .forEach(tr => tr.classList.remove('done-pending'));
  }

  // -- Done dialog (one shared <dialog>, created lazily on first use;
  // collects an optional close rationale sent with the done POST) --
  let doneDialog = null;
  let doneCtx = null;  // {tr, td, n} of the row being closed

  function ensureDoneDialog() {
    if (doneDialog) return doneDialog;
    const dlg = document.createElement('dialog');
    dlg.id = 'done-dialog';
    dlg.innerHTML =
      '<h2 id="done-dlg-head">Mark done</h2>' +
      '<div class="dlg-title" id="done-dlg-title"></div>' +
      '<textarea id="done-note" placeholder="Rationale or instructions ' +
      'for Emise (optional)"></textarea>' +
      '<div id="done-err"></div>' +
      '<div class="dlg-btns">' +
      '<button type="button" id="done-cancel-btn">Cancel</button>' +
      '<button type="button" id="done-confirm-btn">Mark done</button>' +
      '</div>';
    document.body.appendChild(dlg);
    dlg.querySelector('#done-cancel-btn')
      .addEventListener('click', () => dlg.close());
    dlg.querySelector('#done-confirm-btn')
      .addEventListener('click', submitDone);
    // Backdrop click closes without queueing anything (Esc does too,
    // natively). Only a "Mark done" click ever POSTs.
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
    doneDialog = dlg;
    return dlg;
  }

  function onDoneClick(tr, td, n) {
    const dlg = ensureDoneDialog();
    doneCtx = { tr: tr, td: td, n: n };
    dlg.querySelector('#done-dlg-head').textContent = 'Mark #' + n + ' done';
    const titleCell = tr.querySelector('td.title');
    dlg.querySelector('#done-dlg-title').textContent =
      titleCell ? titleCell.textContent : '';
    const note = dlg.querySelector('#done-note');
    note.value = '';
    dlg.querySelector('#done-err').textContent = '';
    const confirm = dlg.querySelector('#done-confirm-btn');
    confirm.disabled = false;
    confirm.textContent = 'Mark done';
    dlg.showModal();
    note.focus();
  }

  function submitDone() {
    if (!doneCtx) return;
    const dlg = doneDialog;
    const ctx = doneCtx;
    const confirm = dlg.querySelector('#done-confirm-btn');
    const errLine = dlg.querySelector('#done-err');
    confirm.disabled = true;
    confirm.textContent = '…';
    errLine.textContent = '';
    const note = dlg.querySelector('#done-note').value;
    api('POST', '/api/items/' + ctx.n + '/done', { note: note }, true)
      .then(res => {
        if (res.status === 201) {
          doneCtx = null;
          dlg.close();
          ctx.tr.classList.add('done-pending');
          ctx.td.innerHTML =
            '<span class="done-note">done — pending Emise’s closure pass</span>';
        } else {
          // Keep the dialog (and the typed note) open; the row is
          // NOT marked — nothing was queued.
          confirm.disabled = false;
          confirm.textContent = 'Mark done';
          errLine.textContent = 'Marking #' + ctx.n + ' done failed (' +
            res.status + ') — NOT queued.';
          if (res.status === 401) refreshSession();
        }
      });
  }

  async function loadResolutions() {
    // Reflect marks already queued (e.g. from another device) so a row
    // Will already marked does not invite a second click.
    const res = await api('GET', '/api/resolutions');
    if (res.status !== 200 || !res.data) return;
    const doneNums = {};
    res.data.atoms.forEach(a => { doneNums[a.register_number] = true; });
    document.querySelectorAll('#grid tbody tr[data-n]').forEach(tr => {
      const n = tr.getAttribute('data-n');
      if (!doneNums[n]) return;
      tr.classList.add('done-pending');
      const td = tr.querySelector('td.done-cell');
      if (td) td.innerHTML =
        '<span class="done-note">done — pending Emise’s closure pass</span>';
    });
  }

  refreshSession();
</script>
</body>
</html>
"""

ROW = """      <tr data-n="{n}"><td class="num">{n}</td><td class="title">{title}</td>
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
    numbers_path = Path(args.out).with_name("register-numbers.json")
    numbers_path.write_text(
        json.dumps(sorted(it["n"] for it in items)) + "\n",
        encoding="utf-8")
    print(f"wrote {args.out}: {len(items)} items "
          f"(header count {header_count}, mirror {len(mirror)}), "
          f"generated {generated}")
    print(f"wrote {numbers_path}: open register numbers for the "
          f"register service's Done validation")


if __name__ == "__main__":
    main()
