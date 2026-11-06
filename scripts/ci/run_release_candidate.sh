#!/usr/bin/env bash
# Compatibility entrypoint; release sequencing is owned by ci/run_release.py.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$repo_root/ci/run_release.py" candidate "$@"
