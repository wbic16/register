# Register UI — register.phext.io

A read-only web grid of the Waiting-on-Will register: every open item,
oldest first, with the exact action needed, waiting-since date, and age
in days. Built for glancing at from a laptop.

## Files

- `generate_register_page.py` — the generator (python3, stdlib only).
  Parses the register of record (`~/workspace/your_files/waiting-on-will.md`:
  numbers, titles, since-dates, count cross-checked against the register
  header) and enriches each row with the curated action + tier from the
  todo.phext mirror source (`~/workspace/phext/todo-source.json`). Emits
  one self-contained HTML file — no frameworks, no build chain.
- `index.html` — the generated page (regenerate, don't hand-edit).
- `deploy/` — awsbox install pack: HTTP bootstrap vhost, final HTTPS
  vhost pair, and `install-on-box.sh`, the single sudo script that wires
  nginx + Let's Encrypt (dry-run first, one production issuance).

## Refresh the page

```sh
python3 generate_register_page.py --out index.html
scp index.html wbic16@awsbox:/sites/web/register.phext.io/index.html
```

(awsbox is reached over the tailnet; /sites/web is wbic16-writable, so
refreshing the page needs no sudo. Only the first install does.)

## First install

Stage `index.html` into `/sites/web/register.phext.io/` and `deploy/`
into `~/register-deploy/` on awsbox, make sure `register.phext.io`
resolves to the box, then on the box:

```sh
bash ~/register-deploy/install-on-box.sh
```
