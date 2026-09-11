#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

candidate_sha="$(git rev-parse HEAD)"
evidence_dir="${RELEASE_BASELINE_EVIDENCE_DIR:-${TMPDIR:-/tmp}/sports-federation-release-baseline/$candidate_sha}"

python3 ci/check_always_invisible_fields.py
scripts/ci/run_release_baseline.sh
python3 ci/check_release_evidence.py \
  --evidence-dir "$evidence_dir" \
  --commit "$candidate_sha" \
  --require-passing

browser_logs=()
for lane in focus install full; do
  log="$evidence_dir/logs/$lane.log"
  [[ -f "$log" ]] && browser_logs+=("$log")
done
if ((${#browser_logs[@]} == 0)); then
  echo "No browser-capable release logs were produced." >&2
  exit 1
fi
python3 ci/check_browser_release_log.py "${browser_logs[@]}"

echo "Release readiness validation passed for $candidate_sha"
