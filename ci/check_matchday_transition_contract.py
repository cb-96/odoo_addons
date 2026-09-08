#!/usr/bin/env python3
"""Protect transactional match-day command and transition boundaries."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ROOT / "sports_federation_matchday/services/matchday_commands.py"
FOUNDATION = ROOT / "sports_federation_base/models/workflow_transition.py"
PUBLIC_COMMANDS = {
    "open_matchday",
    "report_incident",
    "set_court_status",
    "resolve_incident",
    "record_schedule_deviation",
    "close_matchday",
}
REQUIRED_EVENTS = {
    "matchday_opened",
    "matchday_session_opened",
    "matchday_incident_reported",
    "matchday_court_status_changed",
    "matchday_incident_resolved",
    "matchday_match_deviated",
    "matchday_session_closed",
    "matchday_closed",
}


def class_methods(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "FederationMatchdayCommands":
            return {
                child.name: child
                for child in node.body
                if isinstance(child, ast.FunctionDef)
            }
    return {}


def find_violations(root: Path = ROOT) -> list[str]:
    commands = root / COMMANDS.relative_to(ROOT)
    foundation = root / FOUNDATION.relative_to(ROOT)
    if not foundation.is_file():
        return ["shared workflow transition foundation is missing"]
    if not commands.is_file():
        return ["match-day command service is missing"]
    source = commands.read_text(encoding="utf-8")
    methods = class_methods(commands)
    violations = []
    missing = sorted(PUBLIC_COMMANDS - set(methods))
    if missing:
        violations.append(f"match-day command methods are missing: {missing}")
    for name in sorted(PUBLIC_COMMANDS & set(methods)):
        fragment = ast.get_source_segment(source, methods[name]) or ""
        if "savepoint()" not in fragment:
            violations.append(f"{name} is not transactionally savepoint-bound")
    missing_events = sorted(event for event in REQUIRED_EVENTS if event not in source)
    if missing_events:
        violations.append(f"match-day transition events are missing: {missing_events}")
    for direct in (
        'matchday.sudo().state = "open"',
        'matchday.sudo().state = "closed"',
        'session.sudo().write(',
        'status.sudo().write(',
        'incident.sudo().write(',
        'match.sudo().write(values)',
    ):
        if direct in source:
            violations.append(f"direct operational mutation remains: {direct}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Match-day transition contract failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Match-day transition contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
