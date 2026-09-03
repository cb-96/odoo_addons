#!/usr/bin/env python3
"""Validate the product-facing release-candidate qualification contracts."""

from __future__ import annotations

import ast
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def acl_rows():
    rows = []
    for path in ROOT.glob("sports_federation_*/security/ir.model.access.csv"):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(
                dict(row, _path=str(path.relative_to(ROOT)))
                for row in csv.DictReader(handle)
            )
    return rows


def main():
    errors = []
    role_matrix = load_json("ci/rc_role_matrix.json")
    recovery = load_json("ci/rc_recovery_contract.json")
    profiles = load_json("ci/rc_performance_profiles.json")
    if (
        role_matrix.get("schema_version") != 1
        or recovery.get("schema_version") != 1
        or profiles.get("schema_version") != 1
    ):
        errors.append("all RC contracts must use schema_version 1")

    rows = acl_rows()
    for group, contract in role_matrix["roles"].items():
        group_rows = [row for row in rows if row.get("group_id:id") == group]
        for model in contract.get("can_read", []):
            model_ref = "model_" + model.replace(".", "_")
            if not any(
                row.get("model_id:id", "").split(".")[-1] == model_ref
                and row.get("perm_read") == "1"
                for row in group_rows
            ):
                errors.append(f"{group} lacks declared read access to {model}")
        for key, permission in (
            ("must_not_write", "perm_write"),
            ("must_not_create", "perm_create"),
        ):
            for model in contract.get(key, []):
                model_ref = "model_" + model.replace(".", "_")
                if any(
                    row.get("model_id:id", "").split(".")[-1] == model_ref
                    and row.get(permission) == "1"
                    for row in group_rows
                ):
                    errors.append(f"{group} unexpectedly has {permission} on {model}")

    for name, contract in recovery["workflows"].items():
        path = ROOT / contract["source"]
        if not path.is_file():
            errors.append(f"{name}: missing source {contract['source']}")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        methods = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for action in contract["actions"]:
            if action not in methods:
                errors.append(f"{name}: missing recovery action {action}")

    expected_profiles = {"small", "medium", "large"}
    if set(profiles.get("profiles", {})) != expected_profiles:
        errors.append("performance profiles must define small, medium, and large")
    previous = 0
    for name in ("small", "medium", "large"):
        clubs = profiles.get("profiles", {}).get(name, {}).get("clubs", 0)
        if not isinstance(clubs, int) or clubs <= previous:
            errors.append("performance profile club counts must increase")
        previous = clubs

    required = (
        "sports_federation_demo/tests/test_operator_role_acceptance.py",
        "sports_federation_demo/tests/test_browser_competition_lifecycle.py",
        "sports_federation_demo/tests/test_demo_data_pack.py",
        "docs/RELEASE_PILOT_SCENARIO.md",
        "scripts/ci/run_release_baseline.sh",
        "scripts/ci/run_migration_rehearsal.sh",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            errors.append(f"missing RC evidence surface: {relative}")

    if errors:
        print("RC product readiness failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("RC product readiness contracts passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
