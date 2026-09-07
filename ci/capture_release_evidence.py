#!/usr/bin/env python3
"""Capture complete, SHA-bound evidence for one release validation lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURE_CLASSIFICATIONS = (
    "product_defect",
    "migration_defect",
    "test_defect",
    "fixture_defect",
    "documentation_drift",
    "infrastructure_defect",
    "nondeterministic_test",
    "unsupported_configuration",
    "performance_regression",
    "unclassified",
)


def run(*args: str, root: Path = ROOT) -> str:
    result = subprocess.run(args, cwd=root, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def optional_run(*args: str, root: Path = ROOT) -> str | None:
    try:
        return run(*args, root=root)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tool_versions(root: Path = ROOT) -> dict[str, str | None]:
    return {
        "python": platform.python_version(),
        "git": optional_run("git", "--version", root=root),
        "docker": optional_run("docker", "--version", root=root),
        "docker_compose": optional_run("docker", "compose", "version", root=root),
        "postgres_client": optional_run("psql", "--version", root=root),
    }


def build_evidence(args: argparse.Namespace, root: Path = ROOT) -> dict:
    if args.status == "failed" and not args.failure_classification:
        raise ValueError("Failed lanes require --failure-classification")
    if args.status == "skipped" and not args.skip_reason:
        raise ValueError("Skipped lanes require --skip-reason")
    if args.status != "failed" and args.failure_classification:
        raise ValueError("Only failed lanes may have a failure classification")

    evidence = {
        "schema_version": 2,
        "recorded_at": utc_now(),
        "lane": args.lane,
        "status": args.status,
        "commit": run("git", "rev-parse", "HEAD", root=root),
        "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD", root=root),
        "command": args.command,
        "exit_code": args.exit_code,
        "started_at": args.started_at,
        "finished_at": args.finished_at,
        "duration_seconds": args.duration_seconds,
        "database": args.database,
        "runner": {
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "github_job": os.environ.get("GITHUB_JOB"),
            "host": platform.node(),
            "platform": platform.platform(),
        },
        "tools": tool_versions(root),
        "failure_classification": args.failure_classification,
        "skip_reason": args.skip_reason,
    }
    if args.log:
        evidence["log"] = {
            "path": str(args.log),
            "sha256": sha256(args.log),
            "size_bytes": args.log.stat().st_size,
        }
    if args.backup:
        evidence["backup"] = {
            "path": str(args.backup),
            "sha256": sha256(args.backup),
            "size_bytes": args.backup.stat().st_size,
        }
    return evidence


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", required=True)
    parser.add_argument(
        "--status", choices=("passed", "failed", "skipped"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--finished-at", required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--database")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--failure-classification", choices=FAILURE_CLASSIFICATIONS)
    parser.add_argument("--skip-reason")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        evidence = build_evidence(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
