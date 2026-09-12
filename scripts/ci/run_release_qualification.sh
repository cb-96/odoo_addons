#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

: "${RELEASE_BACKUP_DIR:?Set RELEASE_BACKUP_DIR to an approved production-like backup}"
: "${ROLLBACK_OWNER:?Set ROLLBACK_OWNER}"
: "${ROLLBACK_TRIGGER:?Set ROLLBACK_TRIGGER}"

candidate_sha="$(git rev-parse HEAD)"
baseline_dir="${RELEASE_BASELINE_EVIDENCE_DIR:-${TMPDIR:-/tmp}/sports-federation-release-baseline/$candidate_sha}"
migration_dir="${MIGRATION_EVIDENCE_DIR:-${TMPDIR:-/tmp}/sports-federation-migration/$candidate_sha}"

RELEASE_BASELINE_EVIDENCE_DIR="$baseline_dir" \
  scripts/ci/run_release_readiness.sh

scripts/ci/run_migration_rehearsal.sh \
  --backup-dir "$RELEASE_BACKUP_DIR" \
  --evidence-dir "$migration_dir" \
  --rollback-owner "$ROLLBACK_OWNER" \
  --rollback-trigger "$ROLLBACK_TRIGGER" \
  --yes

python3 ci/check_release_signoff.py \
  --baseline "$baseline_dir/summary.json" \
  --migration "$migration_dir/manifest.json" \
  --commit "$candidate_sha"

echo "Release qualification passed for $candidate_sha"
