#!/usr/bin/env python3
"""Capture release migration counts and integrity checks from PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "ci/release_invariants.json"


def run_sql(database: str, sql: str) -> int:
    command = [
        "psql",
        "--host", os.environ.get("PGHOST", "127.0.0.1"),
        "--port", os.environ.get("PGPORT", "5432"),
        "--username", os.environ.get("PGUSER", "odoo"),
        "--dbname", database,
        "--tuples-only",
        "--no-align",
        "--set", "ON_ERROR_STOP=1",
        "--command", sql,
    ]
    result = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        env={**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "odoo")},
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    value = result.stdout.strip()
    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(f"Invariant query did not return an integer: {value!r}") from error


def validate_contract(contract: dict) -> None:
    if contract.get("schema_version") != 1:
        raise ValueError("Invariant contract schema_version must be 1")
    for section in ("counts", "zero_checks"):
        entries = contract.get(section)
        if not isinstance(entries, dict) or not entries:
            raise ValueError(f"Invariant contract {section} must be a non-empty object")
        for name, query in entries.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Invariant contract {section} has an empty name")
            if not isinstance(query, str) or not query.lstrip().upper().startswith("SELECT"):
                raise ValueError(f"Invariant {name!r} must be a SELECT query")
    modes = contract.get("count_modes", {})
    unknown_modes = set(modes) - set(contract["counts"])
    if unknown_modes:
        raise ValueError(f"Count modes reference unknown counts: {sorted(unknown_modes)}")
    for name in contract["counts"]:
        if modes.get(name, "exact") not in {"exact", "minimum"}:
            raise ValueError(f"Unsupported count mode for {name!r}")


def capture(database: str, contract: dict) -> dict:
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "database": database,
        "count_modes": {
            name: contract.get("count_modes", {}).get(name, "exact")
            for name in sorted(contract["counts"])
        },
        "counts": {
            name: run_sql(database, query)
            for name, query in sorted(contract["counts"].items())
        },
        "zero_checks": {
            name: run_sql(database, query)
            for name, query in sorted(contract["zero_checks"].items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        validate_contract(contract)
        evidence = capture(args.database, contract)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Migration invariant capture failed: {error}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
