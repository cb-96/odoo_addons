#!/usr/bin/env python3
"""Protect the named command boundaries for high-risk federation workflows."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMAND_CONTRACTS = {
    "federation.result.commands": {
        "path": "sports_federation_result_control/services/result_commands.py",
        "methods": {"approve_portal_result", "contest_portal_result"},
    },
    "federation.schedule.approval.commands": {
        "path": "sports_federation_schedule_approval/services/approval_commands.py",
        "methods": {"approve", "publish", "request_changes", "withdraw"},
    },
    "federation.matchday.commands": {
        "path": "sports_federation_matchday/services/matchday_commands.py",
        "methods": {"open_matchday", "close_matchday", "record_schedule_deviation"},
    },
}


def class_contract(path: Path) -> tuple[str | None, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        model_name = None
        methods = {
            child.name
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for child in node.body:
            if not isinstance(child, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "_name"
                for target in child.targets
            ):
                if isinstance(child.value, ast.Constant):
                    model_name = child.value.value
        if model_name:
            return model_name, methods
    return None, set()


def find_violations(root: Path = ROOT) -> list[str]:
    violations = []
    for expected_name, contract in COMMAND_CONTRACTS.items():
        path = root / contract["path"]
        if not path.is_file():
            violations.append(f"{contract['path']}: command service is missing")
            continue
        model_name, methods = class_contract(path)
        if model_name != expected_name:
            violations.append(
                f"{contract['path']}: expected model {expected_name}, got {model_name}"
            )
        missing = sorted(contract["methods"] - methods)
        if missing:
            violations.append(f"{contract['path']}: missing command methods {missing}")
    result_model = (
        root / "sports_federation_result_control/models/match_result_control.py"
    )
    source = result_model.read_text(encoding="utf-8")
    if "if self.env.su:" in source:
        violations.append(
            "result control contains an unconditional superuser authorization bypass"
        )
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Privileged command contract failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Privileged command contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
