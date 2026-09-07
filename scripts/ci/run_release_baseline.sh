#!/usr/bin/env bash
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

evidence_dir="${RELEASE_BASELINE_EVIDENCE_DIR:-$repo_root/artifacts/release/baseline}"
database="${DB_NAME:-sf_rc_validation}"
upgrade_database="${UPGRADE_DB_NAME:-sf_rc_upgrade}"
export RC_COMPOSE_PROJECT="${RC_COMPOSE_PROJECT:-sf_rc_baseline_$(date +%s)_$$}"
export RC_COMPOSE_RETAIN=1
required_lanes=(
  preflight
  static
  install
  upgrade
  core
  portal
  public
  performance
  acceptance
  focus
  full
)
mkdir -p "$evidence_dir/logs"
rm -f "$evidence_dir"/lane-*.json "$evidence_dir/summary.json"

cleanup_rc_compose() {
  RC_COMPOSE_RETAIN=1 scripts/ci/run_rc_validation.sh cleanup >/dev/null 2>&1 || true
}
trap cleanup_rc_compose EXIT

python3 ci/capture_codebase_inventory.py \
  --output "$evidence_dir/codebase-inventory.json"

utc_now() {
  date -u +'%Y-%m-%dT%H:%M:%SZ'
}

failure_classification_for() {
  local lane="$1"
  local variable="RELEASE_FAILURE_CLASSIFICATION_${lane^^}"
  variable="${variable//-/_}"
  printf '%s' "${!variable:-unclassified}"
}

record_lane() {
  local lane="$1"
  local status="$2"
  local exit_code="$3"
  local started_at="$4"
  local finished_at="$5"
  local duration="$6"
  local log_file="$7"
  local lane_database="$database"
  if [[ "$lane" == "upgrade" ]]; then
    lane_database="$upgrade_database"
  fi
  local command="scripts/ci/run_rc_validation.sh $lane"
  local args=(
    --lane "$lane"
    --status "$status"
    --command "$command"
    --exit-code "$exit_code"
    --started-at "$started_at"
    --finished-at "$finished_at"
    --duration-seconds "$duration"
    --database "$lane_database"
    --log "$log_file"
    --output "$evidence_dir/lane-$lane.json"
  )
  if [[ "$status" == "failed" ]]; then
    args+=(--failure-classification "$(failure_classification_for "$lane")")
  fi
  python3 ci/capture_release_evidence.py "${args[@]}"
}

prepare_upgrade_database() {
  local log_file="$evidence_dir/logs/upgrade-install.log"
  echo "[Release baseline] Preparing upgrade database: $upgrade_database" | tee "$log_file"
  DB_NAME="$upgrade_database" \
    ODOO_LOGFILE="$log_file" \
    scripts/ci/run_rc_validation.sh install 2>&1 | tee -a "$log_file"
}

run_lane() {
  local lane="$1"
  local log_file="$evidence_dir/logs/$lane.log"
  local started_at finished_at started_epoch finished_epoch exit_code status
  started_at="$(utc_now)"
  started_epoch="$(date +%s)"
  echo "[Release baseline] Running RC lane: $lane" | tee "$log_file"
  scripts/ci/run_rc_validation.sh "$lane" 2>&1 | tee -a "$log_file"
  exit_code=${PIPESTATUS[0]}
  finished_epoch="$(date +%s)"
  finished_at="$(utc_now)"
  status=passed
  if (( exit_code != 0 )); then
    status=failed
  fi
  record_lane \
    "$lane" \
    "$status" \
    "$exit_code" \
    "$started_at" \
    "$finished_at" \
    "$((finished_epoch - started_epoch))" \
    "$log_file"
  if [[ "$status" == "failed" ]]; then
    echo "[Release baseline] Lane failed: $lane" >&2
  fi
  return "$exit_code"
}

# Run every lane so a candidate produces a complete failure picture rather than
# stopping at the first defect. Each failure is explicit and SHA-bound.
overall_status=0
for lane in "${required_lanes[@]}"; do
  if [[ "$lane" == "upgrade" ]]; then
    if ! prepare_upgrade_database; then
      echo "[Release baseline] Upgrade database preparation failed." >&2
      overall_status=1
    fi
  fi
  run_lane "$lane"
  lane_status=$?
  if (( lane_status != 0 )); then
    overall_status=1
  fi
done

finalize_args=(
  --evidence-dir "$evidence_dir"
  --output "$evidence_dir/summary.json"
  --repo "$repo_root"
)
for lane in "${required_lanes[@]}"; do
  finalize_args+=(--required-lane "$lane")
done
python3 ci/finalize_release_evidence.py "${finalize_args[@]}"
summary_status=$?
if (( summary_status != 0 )); then
  overall_status=1
fi

echo "[Release baseline] Evidence: $evidence_dir"
if (( overall_status != 0 )); then
  echo "[Release baseline] Qualification failed. Review summary.json and lane logs." >&2
  exit 1
fi

echo "[Release baseline] Qualification passed."
