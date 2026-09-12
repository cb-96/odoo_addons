#!/usr/bin/env python3
"""Validate destructive, replay-safe, and runtime SQL boundaries."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "ci/contracts/reliability_contract.json"
SQL = re.compile(r"\.execute\s*\(")
MIGRATION_PARTS = {"migrations", "tests"}


def load_contract(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    return document


def source_contains(path: Path, tokens: list[str]) -> list[str]:
    if not path.is_file():
        return [f"missing file: {path.relative_to(ROOT)}"]
    source = path.read_text(encoding="utf-8")
    return [
        f"{path.relative_to(ROOT)} missing {token}"
        for token in tokens
        if token not in source
    ]


def violations(root: Path, contract: dict) -> list[str]:
    failures: list[str] = []
    test_file = (
        root / "sports_federation_matchday/tests/test_matchday_operator_handoff.py"
    )
    failures += source_contains(
        test_file,
        contract["destructive_operations"]["required_tests"],
    )
    capabilities = contract["idempotency"]["required_capabilities"]
    capability_files = {
        "schedule_commands": root
        / "sports_federation_scheduling/services/schedule_commands.py",
        "standing_recompute": root
        / "sports_federation_standings/models/standing_recompute_job.py",
        "integration_delivery": root
        / "sports_federation_import_tools/models/integration_delivery_stage_mixin.py",
        "finance_events": root
        / "sports_federation_finance_bridge/models/finance_event.py",
    }
    for name, tokens in capabilities.items():
        failures += source_contains(capability_files[name], tokens)

    allowed = set(contract["sql_boundaries"]["allowed_runtime_files"])
    prefixes = tuple(contract["sql_boundaries"].get("allowed_runtime_prefixes", []))
    for addon in sorted(root.glob("sports_federation_*")):
        for path in sorted(addon.rglob("*.py")):
            relative = path.relative_to(root)
            if MIGRATION_PARTS.intersection(relative.parts):
                continue
            source = path.read_text(encoding="utf-8")
            relative_name = relative.as_posix()
            if (
                SQL.search(source)
                and relative_name not in allowed
                and not relative_name.startswith(prefixes)
            ):
                failures.append(f"unregistered runtime SQL: {relative_name}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    try:
        contract = load_contract(args.contract)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Reliability contract is invalid: {exc}")
        return 1
    failures = violations(ROOT, contract)
    if failures:
        print("Reliability contract failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Reliability contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
