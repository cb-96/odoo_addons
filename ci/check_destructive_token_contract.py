#!/usr/bin/env python3
"""Protect process-local destructive authorization tokens from contract drift."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOKEN_MODULE = ROOT / "sports_federation_base" / "destructive_tokens.py"
TOKEN_NAME = "MATCHDAY_DESTRUCTIVE_DELETE_TOKEN"
CONTEXT_NAME = "MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY"
ALLOWED_MODULES = {
    "sports_federation_matchday/models/matchday_restart.py",
    "sports_federation_matchday/models/matchday_session.py",
    "sports_federation_matchday/models/operational_control.py",
    "sports_federation_matchday/wizards/matchday_delete_wizard.py",
    "sports_federation_schedule_approval/models/publication_integrity.py",
    "sports_federation_scheduling/models/schedule_integrity.py",
}


def imported_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if (
            node.module
            != "odoo.addons.sports_federation_base.destructive_tokens"
        ):
            continue
        names.update(alias.name for alias in node.names)
    return names


def find_violations(root: Path = ROOT) -> list[str]:
    violations = []
    for path in sorted(root.glob("sports_federation_*/**/*.py")):
        rel = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        if (
            TOKEN_NAME not in source
            and "matchday_destructive_delete_token" not in source
        ):
            continue
        if path == TOKEN_MODULE:
            continue
        if rel not in ALLOWED_MODULES:
            violations.append(
                f"{rel}: destructive token use is not an approved boundary"
            )
            continue
        tree = ast.parse(source, filename=str(path))
        imports = imported_names(tree)
        missing = {TOKEN_NAME, CONTEXT_NAME} - imports
        if missing:
            violations.append(
                f"{rel}: missing token-contract imports {sorted(missing)}"
            )
        if (
            '"matchday_destructive_delete_token"' in source
            or "'matchday_destructive_delete_token'" in source
        ):
            violations.append(f"{rel}: destructive context key must use {CONTEXT_NAME}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Destructive token contract failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Destructive token contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
