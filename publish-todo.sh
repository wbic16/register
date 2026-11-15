#!/bin/bash
# Republish todo.phext to wbic16/exo-plan@exo from aletheia-core.
# Expects the new file at ~/todo.phext.new. Force push never used.
set -euo pipefail
DIR=~/exo-plan-publish
if [ ! -d "$DIR/.git" ]; then
  git clone git@github.com:wbic16/exo-plan.git "$DIR"
fi
cd "$DIR"
git fetch origin
git checkout exo
git reset --hard origin/exo
cp ~/todo.phext.new todo.phext
if git diff --quiet -- todo.phext; then
  echo "NO CHANGE — remote already carries this todo.phext"
  sha256sum todo.phext
  exit 0
fi
git add todo.phext
git commit -m "todo.phext: register mirror update"
git push origin exo
git fetch origin
echo "local:  $(sha256sum todo.phext | cut -d' ' -f1)"
echo "remote: $(git show origin/exo:todo.phext | sha256sum | cut -d' ' -f1)"
echo "head:   $(git rev-parse HEAD)"
