#!/usr/bin/env python3
"""Validate baseline and migration evidence as one release decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(str(path) + ": expected a JSON object")
    return value


def validate(baseline: dict, migration: dict, expected_commit: str) -> list[str]:
    failures = []
    if baseline.get("commit") != expected_commit:
        failures.append("baseline evidence belongs to another commit")
    if baseline.get("status") != "passed" or baseline.get("complete") is not True:
        failures.append("baseline evidence is not passing and complete")
    for key in (
        "failed_lanes",
        "skipped_lanes",
        "commit_mismatches",
        "invalid_records",
        "missing_lanes",
        "unexpected_lanes",
    ):
        if baseline.get(key):
            failures.append(f"baseline contains {key}")
    if migration.get("commit") != expected_commit:
        failures.append("migration evidence belongs to another commit or has no commit")
    if migration.get("status") != "passed":
        failures.append("migration rehearsal did not pass")
    if not str(migration.get("rollback_owner") or "").strip():
        failures.append("migration evidence has no rollback owner")
    if not str(migration.get("rollback_trigger") or "").strip():
        failures.append("migration evidence has no rollback trigger")
    backup = migration.get("backup", {})
    if not backup.get("sha256"):
        failures.append("migration evidence has no backup checksum")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--migration", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        failures = validate(
            read_json(args.baseline), read_json(args.migration), args.commit
        )
        try:
            from .migration_evidence import validate_bundle
        except ImportError:
            from migration_evidence import validate_bundle
        failures.extend(validate_bundle(args.migration.parent, args.commit))
    except (OSError, ValueError, TypeError) as exc:
        print(f"Release sign-off evidence cannot be read: {exc}")
        return 1
    if failures:
        print("Release sign-off validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Release sign-off evidence passed for {args.commit}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
