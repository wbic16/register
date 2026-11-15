# register

Builders for the phext registers: each `build_*_phext.py` rebuilds one
register's `.phext` from its source JSON (`--check` verifies the committed
phext matches its source). `costs_tick.py` appends ticks to the costs
ledger; `publish-todo.sh` / `run-publish-todo.sh` publish the todo
register.

Live copies run from `~/workspace/phext/` on the Muse VM, invoked by the
register workflows and crons (artifact inscription, costs ledger, lessons
freshness guard, jobs/contests/mastery rollups). This repo is the source
home for the builders the 2026-11-15 repo-coverage census found untracked;
the six sibling builders already tracked in wbic16/emise-tools stay there.
