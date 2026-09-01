#!/usr/bin/env python3
"""Validate the versioned release-performance qualification contract."""
from __future__ import annotations
import ast
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ci/performance_budgets.json"

def main() -> int:
    errors = []
    try:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Performance qualification contract is unreadable: {error}", file=sys.stderr)
        return 1
    if contract.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    budgets = contract.get("budgets")
    if not isinstance(budgets, dict) or not budgets:
        errors.append("budgets must be a non-empty object")
        budgets = {}
    else:
        for name, value in budgets.items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                errors.append(f"budget {name!r} must be a positive integer")
    required_files = contract.get("required_test_files")
    if not isinstance(required_files, list) or not required_files:
        errors.append("required_test_files must be a non-empty list")
        required_files = []
    for relative in required_files:
        if not (ROOT / relative).is_file():
            errors.append(f"missing performance test file: {relative}")
    required_classes = contract.get("required_test_classes", {})
    if not isinstance(required_classes, dict):
        errors.append("required_test_classes must be an object")
        required_classes = {}
    for relative, class_names in required_classes.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as error:
            errors.append(f"cannot inspect {relative}: {error}")
            continue
        available = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        for class_name in class_names:
            if class_name not in available:
                errors.append(f"missing performance test class {class_name} in {relative}")
    if errors:
        print("Performance qualification contract failed:", file=sys.stderr)
        for error in errors: print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Performance qualification contract passed: {len(budgets)} budgets, {len(required_files)} test files.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
