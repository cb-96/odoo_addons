#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

evidence_dir="${RELEASE_BASELINE_EVIDENCE_DIR:-$repo_root/artifacts/release/baseline}"
database="${DB_NAME:-sf_rc_validation}"
mkdir -p "$evidence_dir"

record_lane() {
  local lane="$1"
  local status="$2"
  python3 ci/capture_release_evidence.py \
    --lane "$lane" \
    --status "$status" \
    --database "$database" \
    --output "$evidence_dir/$lane.json"
}

run_lane() {
  local lane="$1"
  echo "[Release baseline] Running RC lane: $lane"
  if scripts/ci/run_rc_validation.sh "$lane"; then
    record_lane "$lane" passed
  else
    local exit_code=$?
    record_lane "$lane" failed || true
    echo "[Release baseline] Lane failed: $lane" >&2
    return "$exit_code"
  fi
}

# Qualification is intentionally strict. Run it from the committed candidate
# with no tracked changes or generated runtime configuration in the repository.
run_lane preflight
run_lane static
run_lane install
run_lane core
run_lane portal
run_lane public
run_lane performance
run_lane focus
run_lane full

python3 - "$evidence_dir" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
records = [json.loads(path.read_text()) for path in sorted(root.glob("*.json"))]
summary = {
    "schema_version": 1,
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "status": (
        "passed"
        if records and all(record["status"] == "passed" for record in records)
        else "failed"
    ),
    "lanes": [
        {
            "lane": record["lane"],
            "status": record["status"],
            "commit": record["commit"],
        }
        for record in records
    ],
}
(root / "summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n"
)
print(root / "summary.json")
PY

echo "[Release baseline] Qualification passed."
echo "[Release baseline] Evidence: $evidence_dir"
