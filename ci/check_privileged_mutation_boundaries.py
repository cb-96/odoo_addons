#!/usr/bin/env python3
"""Reject controller-owned writes that elevate with ``sudo()``.

Controllers may use elevated reads only when the existing route-specific guards
allow them. Mutations must cross an owned command or privilege service so the
scope assertion, audit event, and business transaction remain centralized.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MUTATING_METHODS = {"create", "write", "unlink"}
PRIVILEGE_METHODS = {"portal_create", "portal_write", "portal_call"}


def controller_files(root: Path = ROOT) -> list[Path]:
    return sorted(root.glob("sports_federation_*/controllers/**/*.py"))


def contains_sudo(node: ast.AST) -> bool:
    return any(
        isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Attribute)
        and candidate.func.attr == "sudo"
        for candidate in ast.walk(node)
    )


def mutation_name(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Attribute):
        return None
    name = call.func.attr
    if name in MUTATING_METHODS or name.startswith("action_"):
        return name
    return None


def enclosing_function(tree: ast.AST, node: ast.AST) -> str:
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "<module>"


def find_violations(root: Path = ROOT) -> list[str]:
    violations = []
    for path in controller_files(root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            operation = mutation_name(node)
            if not operation or not contains_sudo(node.func.value):
                continue
            # The privilege boundary itself performs the audited elevation. A
            # controller may invoke it but may not reproduce its internals.
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in PRIVILEGE_METHODS
            ):
                continue
            violations.append(
                f"{path.relative_to(root).as_posix()}:{node.lineno} "
                f"{enclosing_function(tree, node)} uses sudo().{operation}()"
            )
    return sorted(violations)


def main() -> int:
    violations = find_violations()
    if violations:
        print(
            "Privileged mutation boundary check failed. Move these writes to an "
            "owned command or privilege service:",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Privileged mutation boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
