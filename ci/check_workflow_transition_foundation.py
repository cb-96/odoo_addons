#!/usr/bin/env python3
"""Protect the shared workflow transition and its initial adopters."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "sports_federation_base/models/workflow_transition.py"
APPROVAL_COMMANDS = (
    ROOT
    / "sports_federation_schedule_approval/services/approval_commands.py"
)
REQUIRED_ARGUMENTS = {
    "target_state",
    "allowed_from",
    "reason_required",
    "expected_revision",
    "forbidden_actor_fields",
    "writer",
    "event_type",
}


def execute_arguments(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "execute":
            return {argument.arg for argument in node.args.args}
    return set()


def find_violations(root: Path = ROOT) -> list[str]:
    violations = []
    foundation = root / FOUNDATION.relative_to(ROOT)
    approval = root / APPROVAL_COMMANDS.relative_to(ROOT)
    if not foundation.is_file():
        return ["shared workflow transition service is missing"]
    missing = REQUIRED_ARGUMENTS - execute_arguments(foundation)
    if missing:
        violations.append(f"workflow transition execute() is missing {sorted(missing)}")
    if approval.is_file():
        source = approval.read_text(encoding="utf-8")
        if source.count('self.env["federation.workflow.transition"]') < 3:
            violations.append(
                "schedule approval decisions are not using the transition foundation"
            )
        for direct_write in (
            'review.schedule_id.sudo().state = "approved"',
            'review.schedule_id.sudo().state = "changes_requested"',
            'live.sudo().write({"state": "superseded"})',
        ):
            if direct_write in source:
                violations.append(
                    f"schedule approval retains direct state mutation: {direct_write}"
                )
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Workflow transition foundation check failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Workflow transition foundation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
