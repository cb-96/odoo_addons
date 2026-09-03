#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$root"
backup=""
while (($#)); do case "$1" in --backup-dir) backup="${2:-}"; shift 2;; *) echo "Usage: $0 [--backup-dir PATH]" >&2; exit 2;; esac; done
python3 ci/check_rc_product_readiness.py
python3 ci/check_rc_usability.py
scripts/ci/run_release_baseline.sh
if [[ -n "$backup" ]]; then scripts/ci/run_migration_rehearsal.sh --backup-dir "$backup"; else echo "[RC] Migration rehearsal skipped: no approved backup supplied."; fi
