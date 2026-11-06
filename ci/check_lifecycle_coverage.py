#!/usr/bin/env python3
"""Check the end-to-end competition lifecycle tests against their contract.

``--source`` confirms every required test method exists in the contracted file,
carries the required tags, is registered for discovery and uses no shortcut
(elevation, policy bypass, direct workflow-state writes, skips).

``--log`` confirms every required method actually started in an Odoo run and
that the run reported no failure or error. A tag that selects nothing makes
Odoo exit successfully, so a green exit code alone is not evidence.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ci" / "release_confidence" / "competition_lifecycle.json"
START = re.compile(r"Starting\s+(?:[\w.]+\.)?(?P<cls>\w+)\.(?P<method>test_\w+)\s+\.\.\.")
FAILURE = re.compile(r"\b(?:FAIL|ERROR):\s*(?:[\w.]+\.)?(?P<cls>\w+)\.(?P<method>test_\w+)")
RESULT = re.compile(r"(?P<failed>\d+)\s+failed,\s+(?P<errors>\d+)\s+error\(s\)\s+of\s+(?P<total>\d+)\s+tests")


def load_contract(path: Path = CONTRACT) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"Unsupported contract schema in {path}")
    return data


def _tag_values(node: ast.AST) -> set[str]:
    values = set()
    for decorator in getattr(node, "decorator_list", []):
        if isinstance(decorator, ast.Call) and getattr(decorator.func, "id", "") == "tagged":
            values.update(
                arg.value for arg in decorator.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            )
    return values


def check_source(contract: dict, root: Path = ROOT) -> list[str]:
    spec = contract["test"]
    path = root / spec["path"]
    if not path.is_file():
        return [f"{spec['path']}: missing; the lifecycle scenarios have not been implemented"]
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    methods: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            tags = _tag_values(node)
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                    methods[item.name] = tags
    for required in spec["required_methods"]:
        name = required["name"]
        if name not in methods:
            errors.append(f"{spec['path']}: missing required test {name}")
            continue
        missing_tags = set(spec["required_tags"]) - methods[name]
        if missing_tags:
            errors.append(f"{spec['path']}: {name} lacks tags {sorted(missing_tags)}")
    for rule in spec["forbidden_patterns"]:
        for number, line in enumerate(text.splitlines(), 1):
            if re.search(rule["pattern"], line):
                errors.append(f"{spec['path']}:{number}: {rule['reason']}")
    init = path.parent / "__init__.py"
    module = path.stem
    if not init.is_file() or not re.search(
        rf"^from \. import {re.escape(module)}\b", init.read_text(encoding="utf-8"), re.M
    ):
        errors.append(f"{init.relative_to(root)}: does not import {module}")
    return errors


def check_log(contract: dict, log_path: Path) -> list[str]:
    if not log_path.is_file():
        return [f"{log_path}: log missing"]
    text = log_path.read_text(encoding="utf-8", errors="replace")
    started = {match.group("method") for match in START.finditer(text)}
    failed = {match.group("method") for match in FAILURE.finditer(text)}
    errors: list[str] = []
    for required in contract["test"]["required_methods"]:
        name = required["name"]
        if name not in started:
            errors.append(f"{name}: did not run")
        elif name in failed:
            errors.append(f"{name}: failed")
    results = list(RESULT.finditer(text))
    if not results:
        errors.append("no Odoo test result summary in the log")
    else:
        last = results[-1]
        if int(last.group("failed")) or int(last.group("errors")):
            errors.append(
                f"run reported {last.group('failed')} failed and {last.group('errors')} error(s)"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true", help="check the test source")
    parser.add_argument("--log", type=Path, help="check an Odoo lifecycle-lane log")
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    args = parser.parse_args(argv)
    if not args.source and not args.log:
        parser.error("use --source, --log, or both")
    contract = load_contract(args.contract)
    errors: list[str] = []
    if args.source:
        errors += check_source(contract)
    if args.log:
        errors += check_log(contract, args.log)
    for error in errors:
        print(f"[lifecycle] {error}", file=sys.stderr)
    if errors:
        return 1
    print(
        f"[lifecycle] {len(contract['test']['required_methods'])} required scenarios "
        + ("present" if not args.log else "ran and passed")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
