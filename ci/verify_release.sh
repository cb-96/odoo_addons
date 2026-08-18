#!/usr/bin/env bash
set -euo pipefail
python3 ci/static_checks.py
find sports_federation_* -type f -name '*.js' -print0 | xargs -0 -r -n1 node --check
git diff --check
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked worktree changes are not allowed in a release artifact." >&2
  exit 1
fi
