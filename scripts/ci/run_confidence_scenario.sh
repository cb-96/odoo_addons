#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
: "${SF_CONFIDENCE_RUN_ID:?Run through ci/release_confidence.py scenario}"
: "${SF_CONFIDENCE_ARTIFACTS:?Missing scenario evidence directory}"
: "${RC_COMPOSE_PROJECT:?Missing generated CI project}"
: "${DB_NAME:?Missing generated database}"
[[ "$RC_COMPOSE_PROJECT" == "$SF_CONFIDENCE_RUN_ID" ]] || { echo 'Project does not match the isolated run' >&2; exit 2; }
[[ "$DB_NAME" == "${SF_CONFIDENCE_RUN_ID}_install" ]] || { echo 'Database does not match the isolated run' >&2; exit 2; }
if [[ $# -eq 2 && "$1" == '--test-tags' ]]; then
  export RC_CONFIDENCE_TEST_TAGS="$2"
elif [[ $# -eq 0 ]]; then
  export RC_CONFIDENCE_TEST_TAGS=sf_release_confidence
else
  echo 'Usage: run_confidence_scenario.sh [--test-tags ODOO_TAGS]' >&2
  exit 2
fi
export RC_COMPOSE_RETAIN=1
export ODOO_LOGFILE="$SF_CONFIDENCE_ARTIFACTS/odoo-scenario.log"
cleanup() {
  bash scripts/ci/run_rc_validation.sh cleanup > "$SF_CONFIDENCE_ARTIFACTS/cleanup.log" 2>&1 || true
}
trap cleanup EXIT
bash scripts/ci/run_rc_validation.sh prepare
bash scripts/ci/run_rc_validation.sh confidence
