#!/usr/bin/env python3
"""Validate curated constraint/index contracts for major federation models."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = REPO_ROOT / "ci" / "contracts" / "constraint_index_contracts.json"


class ModelFileContractInspector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.indexed_fields: set[str] = set()
        self.constraint_symbols: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        if not node.targets:
            return
        target = node.targets[0]
        target_name = target.id if isinstance(target, ast.Name) else None

        value = node.value
        if isinstance(value, ast.Call):
            func = value.func
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and func.value.id == "fields":
                    has_index_true = any(
                        kw.arg == "index"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                        for kw in value.keywords
                    )
                    if has_index_true and target_name:
                        self.indexed_fields.add(target_name)

                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "models"
                    and func.attr == "Constraint"
                    and target_name
                ):
                    self.constraint_symbols.add(target_name)

        self.generic_visit(node)


def _load_contracts() -> list[dict[str, object]]:
    data = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    contracts = data.get("contracts", [])
    if not isinstance(contracts, list):
        raise SystemExit("Invalid constraint/index contract file format.")
    return contracts


def _inspect_source(relative_path: str) -> ModelFileContractInspector:
    source_path = REPO_ROOT / relative_path
    if not source_path.exists():
        raise SystemExit(f"Contract source file not found: {relative_path}")

    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=relative_path)
    inspector = ModelFileContractInspector()
    inspector.visit(tree)
    return inspector


def main() -> int:
    if not CONTRACT_FILE.exists():
        print(f"Missing contract file: {CONTRACT_FILE}")
        return 1

    failures: list[str] = []
    for contract in _load_contracts():
        source = str(contract.get("source", ""))
        model = str(contract.get("model", "unknown"))
        required_indexed_fields = set(contract.get("required_indexed_fields", []))
        required_constraint_symbols = set(
            contract.get("required_constraint_symbols", [])
        )

        inspector = _inspect_source(source)
        missing_indexes = sorted(required_indexed_fields - inspector.indexed_fields)
        missing_constraints = sorted(
            required_constraint_symbols - inspector.constraint_symbols
        )

        if missing_indexes or missing_constraints:
            details: list[str] = []
            if missing_indexes:
                details.append(f"missing indexed fields: {', '.join(missing_indexes)}")
            if missing_constraints:
                details.append(
                    f"missing constraint symbols: {', '.join(missing_constraints)}"
                )
            failures.append(f"- {model} ({source}): {'; '.join(details)}")

    if failures:
        print("Constraint/index contract validation failed:\n")
        print("\n".join(failures))
        return 1

    print("Constraint/index contracts validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
