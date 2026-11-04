#!/usr/bin/env bash
# Run the full end-to-end release check for the current commit.
#
#   automated  release lanes (incl. the lifecycle scenarios), evidence checks,
#              and the migration rehearsal when a backup is supplied
#   serve      start a disposable walkthrough server, seed it, write the agent handoff
#   verify     combine automated, walkthrough and human evidence into one verdict
#   stop       remove the walkthrough server and its database
#   all        automated, then serve (the agent and verify follow)
#
# Environment:
#   E2E_EVIDENCE_DIR     evidence directory outside the repository
#                        (default: $TMPDIR/sports-federation-release-baseline/<sha>)
#   RELEASE_BACKUP_DIR, ROLLBACK_OWNER, ROLLBACK_TRIGGER
#                        all three enable the migration rehearsal and sign-off
#   SF_WALKTHROUGH_PORT  host port for the walkthrough server (default 18069)
#   E2E_LEVEL            verify level: technical | release (default release)
set -uo pipefail

command="${1:-}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

candidate_sha="$(git rev-parse HEAD)"
short_sha="${candidate_sha:0:12}"
evidence_dir="${E2E_EVIDENCE_DIR:-${TMPDIR:-/tmp}/sports-federation-release-baseline/$candidate_sha}"
evidence_dir="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$evidence_dir")"
walk_dir="$evidence_dir/walkthrough"
walk_port="${SF_WALKTHROUGH_PORT:-18069}"
walk_project="sf_walkthrough_${short_sha}"
walk_db="sf_walkthrough"
walk_config="${TMPDIR:-/tmp}/${walk_project}.conf"

log() { echo "[e2e] $*"; }
die() { echo "[e2e] ERROR: $1" >&2; exit "${2:-1}"; }

case "$evidence_dir/" in
  "$repo_root"/*) die "Evidence directory must be outside the repository: $evidence_dir" 2 ;;
esac

require_tools() {
  local tool
  for tool in git python3 docker curl; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is required" 2
  done
  docker compose version >/dev/null 2>&1 || die "Docker Compose is required" 2
}

require_clean_tree() {
  # Evidence is bound to a commit; uncommitted changes would not be covered.
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    die "Commit or stash tracked changes first; evidence must match $candidate_sha" 2
  fi
}

walk_compose() {
  CI_PROJECT_NAME="$walk_project" \
  CI_POSTGRES_USER="${CI_POSTGRES_USER:-odoo}" \
  CI_POSTGRES_PASSWORD="${CI_POSTGRES_PASSWORD:-odoo}" \
  CI_POSTGRES_DB="${CI_POSTGRES_DB:-postgres}" \
  CI_ODOO_DB_HOST="${CI_ODOO_DB_HOST:-ci-db}" \
  CI_ODOO_DB_PORT="${CI_ODOO_DB_PORT:-5432}" \
  CI_ODOO_CONFIG_PATH="$walk_config" \
  SF_WALKTHROUGH_PORT="$walk_port" \
    docker compose -p "$walk_project" \
      -f ci/docker-compose.ci.yaml -f ci/docker-compose.walkthrough.yaml "$@"
}

# Same privilege drop as run_rc_validation.sh: Odoo never runs as root.
odoo_as_user='set -eu
if [ ! -e /usr/lib/python3/dist-packages/odoo-bin ]; then
  ln -s /usr/bin/odoo /usr/lib/python3/dist-packages/odoo-bin
fi
if command -v gosu >/dev/null 2>&1; then exec gosu odoo odoo "$@"
elif command -v runuser >/dev/null 2>&1; then exec runuser -u odoo -- odoo "$@"
else exec odoo "$@"; fi'

run_automated() {
  require_tools
  require_clean_tree
  mkdir -p "$evidence_dir"
  log "Candidate $candidate_sha; evidence in $evidence_dir"
  local status=0
  if [[ -n "${RELEASE_BACKUP_DIR:-}" && -n "${ROLLBACK_OWNER:-}" && -n "${ROLLBACK_TRIGGER:-}" ]]; then
    log "Running release qualification (lanes, evidence checks, migration rehearsal, sign-off)"
    RELEASE_BASELINE_EVIDENCE_DIR="$evidence_dir" \
      MIGRATION_EVIDENCE_DIR="${MIGRATION_EVIDENCE_DIR:-$evidence_dir/migration}" \
      scripts/ci/run_release_qualification.sh || status=$?
  else
    log "No approved backup supplied: running readiness without migration rehearsal"
    log "Set RELEASE_BACKUP_DIR, ROLLBACK_OWNER and ROLLBACK_TRIGGER for full qualification"
    RELEASE_BASELINE_EVIDENCE_DIR="$evidence_dir" \
      scripts/ci/run_release_readiness.sh || status=$?
  fi
  python3 - "$evidence_dir" "$candidate_sha" "$status" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
evidence, sha, status = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
(evidence / "automated-status.json").write_text(json.dumps({
    "commit": sha,
    "exit_code": status,
    "migration_rehearsal": (evidence / "migration" / "manifest.json").is_file(),
    "finished_at": datetime.now(timezone.utc).isoformat(),
}, indent=2) + "\n", encoding="utf-8")
PY
  if (( status != 0 )); then
    log "Automated checks failed (exit $status). See $evidence_dir/summary.json and logs/."
  else
    log "Automated checks passed."
  fi
  return "$status"
}

wait_for_http() {
  local url="http://127.0.0.1:$walk_port/web/login" attempt
  for attempt in $(seq 1 90); do
    if curl -fsS -o /dev/null "$url"; then return 0; fi
    sleep 2
  done
  return 1
}

run_serve() {
  require_tools
  require_clean_tree
  mkdir -p "$walk_dir/screenshots"
  chmod 700 "$walk_dir"
  log "Preparing disposable walkthrough database $walk_db (project $walk_project)"
  RC_COMPOSE_PROJECT="$walk_project" RC_COMPOSE_RETAIN=1 DB_NAME="$walk_db" \
    RC_ODOO_CONFIG_PATH="$walk_config" ODOO_LOGFILE="$walk_dir/install.log" \
    scripts/ci/run_rc_validation.sh prepare || die "Walkthrough database install failed; see $walk_dir/install.log"

  log "Seeding role accounts and reference data"
  local seed_output
  seed_output="$(walk_compose run --rm -T ci-odoo sh -lc "$odoo_as_user" -- \
    shell -d "$walk_db" --no-http < scripts/ci/seed_walkthrough.py 2> "$walk_dir/seed.log")" \
    || die "Seeding failed; see $walk_dir/seed.log"
  local seed_json
  seed_json="$(grep '^SF_WALKTHROUGH_SEED=' <<<"$seed_output" | tail -n 1 | cut -d= -f2-)"
  [[ -n "$seed_json" ]] || die "Seed produced no report; see $walk_dir/seed.log"

  log "Starting walkthrough server on 127.0.0.1:$walk_port"
  walk_compose run -d --service-ports --name "${walk_project}_web" ci-odoo \
    sh -lc "$odoo_as_user" -- -d "$walk_db" --db-filter="^${walk_db}\$" \
    --http-interface=0.0.0.0 --http-port=8069 --without-demo=True \
    >/dev/null || die "Walkthrough server did not start"
  wait_for_http || die "Walkthrough server is not answering on port $walk_port"

  umask 077
  python3 - "$walk_dir/handoff.json" "$seed_json" <<PY
import json, sys
from pathlib import Path
seed = json.loads(sys.argv[2])
handoff = {
    "schema_version": 1,
    "commit": "$candidate_sha",
    "base_url": "http://127.0.0.1:$walk_port",
    "database": "$walk_db",
    "repository": "$repo_root",
    "evidence_dir": "$evidence_dir",
    "walkthrough_dir": "$walk_dir",
    "output": "$walk_dir/walkthrough.json",
    "contract": "ci/release_confidence/competition_lifecycle.json",
    "accounts": seed["accounts"],
    "seeded": seed["data"],
    "seed_failures": seed["failed_steps"],
    "stop_command": "scripts/ci/run_end_to_end_release.sh stop",
    "verify_command": "scripts/ci/run_end_to_end_release.sh verify",
}
Path(sys.argv[1]).write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if seed["failed_steps"]:
    print("[e2e] Seed steps failed (agent must complete them in the UI):")
    for item in seed["failed_steps"]:
        print(f"[e2e]   {item['step']}: {item['error']}")
PY
  log "Walkthrough server ready: http://127.0.0.1:$walk_port"
  log "Agent handoff (contains disposable passwords): $walk_dir/handoff.json"
  log "Give the agent docs/END_TO_END_RELEASE_AGENT.md, then run: $0 verify"
}

run_verify() {
  local level="${E2E_LEVEL:-release}"
  [[ -f "$evidence_dir/summary.json" ]] || die "No automated evidence in $evidence_dir; run '$0 automated' first" 2
  python3 ci/check_end_to_end_evidence.py --evidence-dir "$evidence_dir" \
    --commit "$candidate_sha" --level "$level"
}

run_stop() {
  require_tools
  walk_compose down -v --remove-orphans >/dev/null 2>&1 || true
  docker rm -f "${walk_project}_web" >/dev/null 2>&1 || true
  rm -f "$walk_config"
  log "Walkthrough server and database removed."
}

case "$command" in
  automated) run_automated ;;
  serve) run_serve ;;
  verify) run_verify ;;
  stop) run_stop ;;
  all)
    run_automated || { log "Not starting the walkthrough: fix the automated failures first."; exit 1; }
    run_serve
    ;;
  *)
    echo "Usage: $0 {automated|serve|verify|stop|all}" >&2
    exit 2
    ;;
esac
