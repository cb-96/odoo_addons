#!/usr/bin/env python3
"""Compare pre-upgrade, post-upgrade, and rollback invariant evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported invariant evidence schema in {path}")
    return payload


def compare(
    reference: dict,
    candidate: dict,
    label: str,
    *,
    force_exact: bool = False,
) -> list[dict]:
    differences = []
    modes = reference.get("count_modes", {})
    for name, expected in sorted(reference.get("counts", {}).items()):
        actual = candidate.get("counts", {}).get(name)
        mode = "exact" if force_exact else modes.get(name, "exact")
        violates = actual is None or (
            actual != expected if mode == "exact" else actual < expected
        )
        if violates:
            differences.append(
                {
                    "kind": "count",
                    "name": name,
                    "mode": mode,
                    "expected": expected,
                    "actual": actual,
                    "evidence": label,
                }
            )
    for name, actual in sorted(candidate.get("zero_checks", {}).items()):
        if actual != 0:
            differences.append(
                {
                    "kind": "integrity",
                    "name": name,
                    "expected": 0,
                    "actual": actual,
                    "evidence": label,
                }
            )
    return differences


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--rollback", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        before = load(args.before)
        after = load(args.after)
        differences = compare(before, after, "after")
        rollback = load(args.rollback) if args.rollback else None
        if rollback:
            differences.extend(compare(before, rollback, "rollback", force_exact=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Migration invariant comparison failed: {error}", file=sys.stderr)
        return 1

    result = {
        "schema_version": 1,
        "compared_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not differences else "failed",
        "before": str(args.before),
        "after": str(args.after),
        "rollback": str(args.rollback) if args.rollback else None,
        "differences": differences,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if differences:
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
