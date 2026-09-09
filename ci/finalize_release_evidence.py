#!/usr/bin/env python3
"""Validate a complete release evidence set and write its summary manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REQUIRED_LANES = (
    "preflight",
    "static",
    "install",
    "upgrade",
    "core",
    "portal",
    "public",
    "performance",
    "acceptance",
    "focus",
    "full",
)


def current_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def load_lane_records(evidence_dir: Path) -> dict[str, dict]:
    records = {}
    for path in sorted(evidence_dir.glob("lane-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        lane = record.get("lane")
        if not lane:
            raise ValueError(f"Evidence has no lane: {path}")
        if lane in records:
            raise ValueError(f"Duplicate evidence for lane: {lane}")
        records[lane] = record
    return records


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def log_is_valid(record: dict) -> bool:
    log = record.get("log", {})
    path_value = log.get("path")
    if not path_value or not log.get("sha256"):
        return False
    path = Path(path_value)
    return (
        path.is_file()
        and path.stat().st_size == log.get("size_bytes")
        and sha256(path) == log.get("sha256")
    )


def build_summary(
    evidence_dir: Path,
    required_lanes: tuple[str, ...],
    expected_commit: str,
) -> dict:
    records = load_lane_records(evidence_dir)
    missing = sorted(set(required_lanes) - set(records))
    unexpected = sorted(set(records) - set(required_lanes))
    commit_mismatches = sorted(
        lane
        for lane, record in records.items()
        if record.get("commit") != expected_commit
    )
    invalid_records = sorted(
        lane
        for lane, record in records.items()
        if record.get("schema_version") != 2
        or record.get("status") not in {"passed", "failed", "skipped"}
        or record.get("exit_code") is None
        or not record.get("command")
        or not record.get("started_at")
        or not record.get("finished_at")
        or record.get("duration_seconds") is None
        or not log_is_valid(record)
        or (
            record.get("status") == "failed"
            and not record.get("failure_classification")
        )
        or (record.get("status") == "skipped" and not record.get("skip_reason"))
    )
    failed = sorted(
        lane for lane, record in records.items() if record.get("status") == "failed"
    )
    skipped = sorted(
        lane for lane, record in records.items() if record.get("status") == "skipped"
    )
    passed = sorted(
        lane for lane, record in records.items() if record.get("status") == "passed"
    )
    complete = (
        not missing and not unexpected and not commit_mismatches and not invalid_records
    )
    status = "passed" if complete and not failed and not skipped else "failed"
    return {
        "schema_version": 2,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "commit": expected_commit,
        "status": status,
        "complete": complete,
        "required_lanes": list(required_lanes),
        "passed_lanes": passed,
        "failed_lanes": failed,
        "skipped_lanes": skipped,
        "missing_lanes": missing,
        "unexpected_lanes": unexpected,
        "commit_mismatches": commit_mismatches,
        "invalid_records": invalid_records,
        "lanes": [records[lane] for lane in sorted(records)],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--required-lane", action="append", dest="required_lanes")
    args = parser.parse_args()
    required_lanes = tuple(args.required_lanes or DEFAULT_REQUIRED_LANES)
    output = args.output or args.evidence_dir / "summary.json"
    summary = build_summary(
        args.evidence_dir,
        required_lanes,
        current_commit(args.repo.resolve()),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(output)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
