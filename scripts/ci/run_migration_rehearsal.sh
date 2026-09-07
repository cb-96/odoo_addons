#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

usage() {
  cat <<'EOF'
Usage: scripts/ci/run_migration_rehearsal.sh --backup-dir PATH [options]

Options:
  --backup-dir PATH       Backup directory produced by the upgrade tooling.
  --target-db NAME        Database restored and upgraded (default: sf_rc_migration).
  --rollback-db NAME      Independent rollback verification database (default: sf_rc_rollback).
  --evidence-dir PATH     Evidence output directory (default: artifacts/release/migration).
  --rollback-owner NAME   Person accountable for the rollback decision.
  --rollback-trigger TEXT Objective condition that requires rollback.
  --skip-filestore        Forwarded to the restore drill.
  --yes, -y               Skip restore confirmation prompts.
  --help, -h              Show this help message.
EOF
}

backup_dir=""
target_db="${MIGRATION_TARGET_DB:-sf_rc_migration}"
rollback_db="${MIGRATION_ROLLBACK_DB:-sf_rc_rollback}"
evidence_dir="${MIGRATION_EVIDENCE_DIR:-$repo_root/artifacts/release/migration}"
rollback_owner="${ROLLBACK_OWNER:-}"
rollback_trigger="${ROLLBACK_TRIGGER:-}"
restore_flags=()
rc_compose_file="${RC_COMPOSE_FILE:-$repo_root/ci/docker-compose.ci.yaml}"
rc_compose_project="${RC_COMPOSE_PROJECT:-sf_rc_migration_$(date +%s)_$$}"
rc_config_path="${RC_ODOO_CONFIG_PATH:-${TMPDIR:-/tmp}/${rc_compose_project}.conf}"
ci_postgres_user="${CI_POSTGRES_USER:-odoo}"
ci_postgres_password="${CI_POSTGRES_PASSWORD:-odoo}"
ci_postgres_db="${CI_POSTGRES_DB:-postgres}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-dir) backup_dir="$2"; shift 2 ;;
    --target-db) target_db="$2"; shift 2 ;;
    --rollback-db) rollback_db="$2"; shift 2 ;;
    --evidence-dir) evidence_dir="$2"; shift 2 ;;
    --rollback-owner) rollback_owner="$2"; shift 2 ;;
    --rollback-trigger) rollback_trigger="$2"; shift 2 ;;
    --skip-filestore) restore_flags+=(--skip-filestore); shift ;;
    --yes|-y) restore_flags+=(--yes); shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$backup_dir" ]] || { echo "--backup-dir is required" >&2; exit 2; }
[[ -n "$rollback_owner" ]] || { echo "--rollback-owner is required" >&2; exit 2; }
[[ -n "$rollback_trigger" ]] || { echo "--rollback-trigger is required" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 2; }
mkdir -p "$evidence_dir"

backup_dir="$(cd "$backup_dir" && pwd)"
dump_file="$(find "$backup_dir" -maxdepth 1 -type f -name '*.dump' -print -quit)"
[[ -n "$dump_file" ]] || { echo "No PostgreSQL dump found in $backup_dir" >&2; exit 2; }

cat > "$rc_config_path" <<EOF
[options]
db_host = ci-db
db_port = 5432
db_user = $ci_postgres_user
db_password = $ci_postgres_password
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
data_dir = /var/lib/odoo
list_db = False
http_interface = 127.0.0.1
without_demo = True
EOF
chmod 0644 "$rc_config_path"
export CI_POSTGRES_USER="$ci_postgres_user"
export CI_POSTGRES_PASSWORD="$ci_postgres_password"
export CI_POSTGRES_DB="$ci_postgres_db"
export CI_ODOO_DB_HOST=ci-db
export CI_ODOO_DB_PORT=5432
export CI_ODOO_CONFIG_PATH="$rc_config_path"
export RC_COMPOSE_FILE="$rc_compose_file"
export RC_COMPOSE_PROJECT="$rc_compose_project"
export RC_COMPOSE_RETAIN=1
export MIGRATION_COMPOSE_FILE="$rc_compose_file"
export MIGRATION_COMPOSE_PROJECT="$rc_compose_project"
export MIGRATION_DB_SERVICE=ci-db
export MIGRATION_DB_USER="$ci_postgres_user"

cleanup_rc_compose() {
  RC_COMPOSE_RETAIN=1 scripts/ci/run_rc_validation.sh cleanup >/dev/null 2>&1 || true
  rm -f "$rc_config_path"
}
trap cleanup_rc_compose EXIT

restore_database() {
  local database="$1"
  local report="$2"
  ci/restore_backup_drill.sh \
    --backup-dir "$backup_dir" \
    --target-db "$database" \
    --compose-file "$rc_compose_file" \
    --project-name "$rc_compose_project" \
    --db-service ci-db \
    --db-user "$ci_postgres_user" \
    --report-file "$report" \
    "${restore_flags[@]}"
}

restore_database "$target_db" "$evidence_dir/restore-before-upgrade.txt"
python3 ci/capture_migration_invariants.py \
  --database "$target_db" \
  --output "$evidence_dir/before-upgrade.json"

if UPGRADE_DB_NAME="$target_db" scripts/ci/run_rc_validation.sh upgrade; then
  upgrade_status=passed
else
  upgrade_status=failed
fi
python3 ci/capture_release_evidence.py \
  --lane migration-upgrade \
  --status "$upgrade_status" \
  --database "$target_db" \
  --backup "$dump_file" \
  --output "$evidence_dir/upgrade.json"
[[ "$upgrade_status" == passed ]] || exit 1

python3 ci/capture_migration_invariants.py \
  --database "$target_db" \
  --output "$evidence_dir/after-upgrade.json"

if DB_NAME="$target_db" scripts/ci/run_rc_validation.sh acceptance; then
  acceptance_status=passed
else
  acceptance_status=failed
fi
python3 ci/capture_release_evidence.py \
  --lane role-separated-acceptance \
  --status "$acceptance_status" \
  --database "$target_db" \
  --output "$evidence_dir/operator-acceptance.json"
[[ "$acceptance_status" == passed ]] || exit 1

restore_database "$rollback_db" "$evidence_dir/restore-rollback.txt"
python3 ci/capture_migration_invariants.py \
  --database "$rollback_db" \
  --output "$evidence_dir/rollback.json"

python3 ci/compare_migration_invariants.py \
  --before "$evidence_dir/before-upgrade.json" \
  --after "$evidence_dir/after-upgrade.json" \
  --rollback "$evidence_dir/rollback.json" \
  --output "$evidence_dir/invariant-comparison.json"

python3 - "$evidence_dir" "$rollback_owner" "$rollback_trigger" "$dump_file" <<'PY'
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
owner, trigger, dump_name = sys.argv[2:]
dump = Path(dump_name)
digest = hashlib.sha256()
with dump.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
manifest = {
    "schema_version": 1,
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "status": "passed",
    "rollback_owner": owner,
    "rollback_trigger": trigger,
    "backup": {"path": str(dump), "sha256": digest.hexdigest()},
    "artifacts": sorted(path.name for path in root.iterdir() if path.is_file()),
}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(root / "manifest.json")
PY

echo "Migration rehearsal passed. Evidence: $evidence_dir"
