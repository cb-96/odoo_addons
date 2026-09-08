#!/usr/bin/env python3
"""Protect result workflow transaction, locking, and transition contracts."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "sports_federation_result_control/models/match_result_control.py"
COMMANDS = ROOT / "sports_federation_result_control/services/result_commands.py"
ACTIONS = {
    "action_submit_result",
    "action_verify_result",
    "action_approve_result",
    "action_contest_result",
    "action_correct_result",
    "action_reset_result_to_draft",
}
EVENTS = {"submitted", "verified", "approved", "contested", "corrected", "reset"}


def methods(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            result[node.name] = node
    return result


def find_violations(root: Path = ROOT) -> list[str]:
    model = root / MODEL.relative_to(ROOT)
    commands = root / COMMANDS.relative_to(ROOT)
    if not model.is_file():
        return ["result-control model is missing"]
    if not commands.is_file():
        return ["result command service is missing"]
    source = model.read_text(encoding="utf-8")
    command_source = commands.read_text(encoding="utf-8")
    found = methods(model)
    violations = []
    for action in sorted(ACTIONS):
        method = found.get(action)
        if not method:
            violations.append(f"result action is missing: {action}")
            continue
        fragment = ast.get_source_segment(source, method) or ""
        if "savepoint()" not in fragment:
            violations.append(f"{action} is not transactionally savepoint-bound")
        if "_lock_result_transition()" not in fragment:
            violations.append(f"{action} does not lock the result row")
        if "_result_transition(" not in fragment:
            violations.append(f"{action} bypasses the shared transition helper")
    missing_events = sorted(
        event for event in EVENTS if f'event_type="{event}"' not in source
    )
    if missing_events:
        violations.append(f"result transition events are missing: {missing_events}")
    for direct in (
        '"result_state": "submitted"',
        '"result_state": "verified"',
        '"result_state": "approved"',
        '"result_state": "contested"',
        '"result_state": "corrected"',
        '"result_state": "draft"',
    ):
        if direct in source:
            violations.append(f"direct result-state mutation remains: {direct}")
    command_methods = methods(commands)
    for portal_method in ("approve_portal_result", "contest_portal_result"):
        method = command_methods.get(portal_method)
        if not method:
            violations.append(f"portal result command is missing: {portal_method}")
            continue
        fragment = ast.get_source_segment(command_source, method) or ""
        if "savepoint()" not in fragment:
            violations.append(f"{portal_method} lacks a transactional savepoint")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Result transition contract failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Result transition contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
