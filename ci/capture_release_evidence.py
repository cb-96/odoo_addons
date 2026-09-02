#!/usr/bin/env python3
"""Write deterministic, machine-readable evidence for an RC command."""

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


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", required=True)
    parser.add_argument("--status", choices=("passed", "failed"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    evidence = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "lane": args.lane,
        "status": args.status,
        "commit": run("git", "rev-parse", "HEAD"),
        "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "database": args.database,
        "python": platform.python_version(),
        "runner": os.environ.get("GITHUB_RUN_ID"),
    }
    if args.backup:
        evidence["backup"] = {"path": str(args.backup), "sha256": sha256(args.backup)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
