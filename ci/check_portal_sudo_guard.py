#!/usr/bin/env python3
"""Enforce documented ownership boundaries around portal ``sudo()`` calls."""

from __future__ import annotations
import argparse
import ast
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTROLLERS = ROOT / "sports_federation_portal" / "controllers"
INVENTORY = ROOT / "docs" / "portal_sudo_inventory.json"
SAFE_TOKENS = (
    "_portal_",
    "portal_privilege",
    "_assert_portal_owns",
    "_assert_result_access",
    "_assert_duty_access",
    "portal_assert_in_domain",
    "club_id",
    "team_id",
    "user_id",
    "user.id",
    "scope_domain",
    "portal_club_scope",
    "portal_team_scope",
    "has_group(",
)


def enclosing_function(tree, node):
    best = None
    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(candidate, "end_lineno", candidate.lineno)
            if candidate.lineno <= node.lineno <= end:
                if best is None or candidate.lineno >= best.lineno:
                    best = candidate
    return best


def observed_entries():
    entries = []
    violations = []
    for path in sorted(CONTROLLERS.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            if node.func.attr != "sudo":
                continue
            statement = node
            parents = {}
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    parents[child] = parent
            while statement in parents and not isinstance(statement, ast.stmt):
                statement = parents[statement]
            start = getattr(statement, "lineno", node.lineno)
            end = getattr(
                statement, "end_lineno", getattr(node, "end_lineno", node.lineno)
            )
            context_start = max(1, start - 15)
            context_end = min(len(lines), end + 15)
            statement_text = "\n".join(lines[start - 1 : end])
            context = "\n".join(lines[context_start - 1 : context_end])
            comments = "\n".join(lines[max(0, start - 3) : min(len(lines), end + 1)])
            function = enclosing_function(tree, node)
            function_name = function.name if function else "<module>"
            reason = ""
            match = re.search(r"#\s*noguard:\s*(.+)", comments)
            if match:
                reason = match.group(1).strip()
            guarded = bool(reason or any(token in context for token in SAFE_TOKENS))
            entry = {
                "file": path.relative_to(ROOT).as_posix(),
                "function": function_name,
                "statement": " ".join(statement_text.split()),
                "reason": reason or "adjacent ownership scope check",
            }
            entries.append(entry)
            if not guarded:
                violations.append(f"{entry['file']}:{node.lineno} in {function_name}")
    return (
        sorted(
            entries,
            key=lambda item: (item["file"], item["function"], item["statement"]),
        ),
        violations,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-inventory", action="store_true")
    args = parser.parse_args()
    entries, violations = observed_entries()
    if violations:
        print("[sudo-guard] Undocumented privileged calls:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    if args.write_inventory:
        INVENTORY.write_text(
            json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[sudo-guard] Wrote {len(entries)} inventory entries.")
        return 0
    if not INVENTORY.is_file():
        print(
            "[sudo-guard] Missing sudo inventory. Run with --write-inventory.",
            file=sys.stderr,
        )
        return 1
    expected = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if expected != entries:
        print(
            "[sudo-guard] Inventory is stale. Run with --write-inventory and review the diff.",
            file=sys.stderr,
        )
        return 1
    print(
        f"[sudo-guard] OK - {len(entries)} privileged calls are documented and guarded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
