#!/usr/bin/env python3
"""Verify that every Odoo test module is imported exactly once."""

from __future__ import annotations
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
for addon in sorted(ROOT.glob("sports_federation_*")):
    tests_dir = addon / "tests"
    if not tests_dir.is_dir():
        continue
    test_modules = set()
    for path in tests_dir.glob("test_*.py"):
        try:
            test_tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(ROOT)}: invalid Python: {exc}")
            continue
        has_tests = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in ast.walk(test_tree)
        )
        if has_tests:
            test_modules.add(path.stem)
    init_file = tests_dir / "__init__.py"
    if not init_file.exists():
        errors.append(f"{tests_dir.relative_to(ROOT)}: missing __init__.py")
        continue
    try:
        tree = ast.parse(init_file.read_text(encoding="utf-8"), filename=str(init_file))
    except SyntaxError as exc:
        errors.append(f"{init_file.relative_to(ROOT)}: invalid Python: {exc}")
        continue
    imported = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 1
        for alias in node.names
        if alias.name.startswith("test_")
    ]
    imported_set = set(imported)
    missing = sorted(test_modules - imported_set)
    stale = sorted(imported_set - test_modules)
    duplicate = sorted({name for name in imported if imported.count(name) > 1})
    if missing:
        errors.append(
            f"{init_file.relative_to(ROOT)}: test files not imported: {', '.join(missing)}"
        )
    if stale:
        errors.append(
            f"{init_file.relative_to(ROOT)}: imports without files: {', '.join(stale)}"
        )
    if duplicate:
        errors.append(
            f"{init_file.relative_to(ROOT)}: duplicate imports: {', '.join(duplicate)}"
        )
if errors:
    print("Odoo test discovery contract failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(1)
print("Odoo test discovery contract passed.")
