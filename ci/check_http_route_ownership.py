#!/usr/bin/env python3
"""Reject duplicate literal HTTP route ownership across Odoo controllers."""

import ast
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOTS = sorted(ROOT.glob("sports_federation_*/controllers"))
owners = defaultdict(list)


def literal_routes(decorator):
    if not isinstance(decorator, ast.Call):
        return []
    func = decorator.func
    if not (
        isinstance(func, ast.Attribute) and func.attr == "route" and decorator.args
    ):
        return []
    value = decorator.args[0]
    nodes = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
    routes = [
        node.value
        for node in nodes
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    methods = ("ANY",)
    for keyword in decorator.keywords:
        if keyword.arg == "methods" and isinstance(
            keyword.value, (ast.List, ast.Tuple)
        ):
            parsed = tuple(
                item.value.upper()
                for item in keyword.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
            methods = parsed or methods
    return [(route, method) for route in routes for method in methods]


for root in CONTROLLER_ROOTS:
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                for route, method in literal_routes(decorator):
                    owners[(route, method)].append(
                        f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                    )

conflicts = {key: refs for key, refs in owners.items() if len(refs) > 1}
if conflicts:
    for (route, method), refs in sorted(conflicts.items()):
        print(
            f"Duplicate HTTP route owner for {method} {route}: {', '.join(refs)}",
            file=sys.stderr,
        )
    raise SystemExit(1)
print(f"HTTP route ownership passed for {len(owners)} literal routes.")
