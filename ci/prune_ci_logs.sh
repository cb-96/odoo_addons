#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
KEEP_RUNS="${1:-30}"

if ! [[ "$KEEP_RUNS" =~ ^[0-9]+$ ]]; then
  echo "KEEP_RUNS must be a non-negative integer" >&2
  exit 2
fi

if (( KEEP_RUNS == 0 )); then
  exit 0
fi

if [[ ! -d "$LOG_DIR" ]]; then
  exit 0
fi

mapfile -t run_dirs < <(
  find "$LOG_DIR" -mindepth 1 -maxdepth 1 -type d \
    | sed "s#^$LOG_DIR/##" \
    | sort -r
)

if (( ${#run_dirs[@]} <= KEEP_RUNS )); then
  exit 0
fi

for run_dir in "${run_dirs[@]:KEEP_RUNS}"; do
  rm -rf "$LOG_DIR/$run_dir"
done
