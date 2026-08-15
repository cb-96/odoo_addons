#!/usr/bin/env python3
"""Validate workflow state/action contracts against code declarations."""

from __future__ import annotations

import ast
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "_workflows" / "contracts" / "workflow_state_contracts.json"


def _resolve_expr(expr: ast.AST, symbols: dict[str, Any]) -> Any:
    if isinstance(expr, ast.Constant):
        return expr.value
    if isinstance(expr, ast.Name):
        return symbols.get(expr.id)
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        return [_resolve_expr(item, symbols) for item in expr.elts]
    if isinstance(expr, ast.Dict):
        result = {}
        for key_node, value_node in zip(expr.keys, expr.values):
            key = _resolve_expr(key_node, symbols)
            value = _resolve_expr(value_node, symbols)
            if key is not None:
                result[key] = value
        return result
    if isinstance(expr, ast.Call):
        # field selections may wrap constants in tuple/list constructors.
        if isinstance(expr.func, ast.Name) and expr.func.id in {"list", "tuple", "set"}:
            if expr.args:
                return _resolve_expr(expr.args[0], symbols)
    return None


def _module_ast(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_symbols(tree: ast.Module) -> dict[str, Any]:
    symbols: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            value = _resolve_expr(node.value, symbols)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols[target.id] = value
    return symbols


def _selection_to_states(selection: Any) -> list[str]:
    states: list[str] = []
    if isinstance(selection, tuple):
        selection = list(selection)
    if not isinstance(selection, list):
        return states
    for item in selection:
        if isinstance(item, tuple):
            item = list(item)
        if isinstance(item, list) and item:
            key = item[0]
            if isinstance(key, str):
                states.append(key)
    return states


def _extract_states(source: dict[str, Any]) -> list[str]:
    file_path = REPO_ROOT / source["file"]
    tree = _module_ast(file_path)
    module_symbols = _module_symbols(tree)

    symbol = source.get("selection_symbol")
    if symbol:
        # Support both module-level and class-level constant selections.
        if symbol in module_symbols:
            return _selection_to_states(module_symbols.get(symbol))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            class_symbols = dict(module_symbols)
            for statement in node.body:
                if isinstance(statement, ast.Assign):
                    value = _resolve_expr(statement.value, class_symbols)
                    for target in statement.targets:
                        if isinstance(target, ast.Name):
                            class_symbols[target.id] = value
            if symbol in class_symbols:
                return _selection_to_states(class_symbols.get(symbol))
        return []

    field_name = source.get("field_name")
    if not field_name:
        return []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        class_symbols = dict(module_symbols)
        for statement in node.body:
            if isinstance(statement, ast.Assign):
                value = _resolve_expr(statement.value, class_symbols)
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        class_symbols[target.id] = value
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == field_name
                for target in statement.targets
            ):
                continue
            if not isinstance(statement.value, ast.Call):
                continue
            call = statement.value
            if not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr != "Selection":
                continue

            selection_expr = None
            if call.args:
                selection_expr = call.args[0]
            for keyword in call.keywords or []:
                if keyword.arg == "selection":
                    selection_expr = keyword.value
            if selection_expr is None:
                return []

            selection = _resolve_expr(selection_expr, class_symbols)
            return _selection_to_states(selection)
    return []


def _extract_actions(source: dict[str, Any]) -> set[str]:
    file_path = REPO_ROOT / source["file"]
    tree = _module_ast(file_path)
    actions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            actions.add(node.name)
    return actions


def _load_contracts() -> list[dict[str, Any]]:
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return list(data.get("contracts") or [])


def main() -> int:
    if not CONTRACT_PATH.exists():
        print(f"[workflow-contracts] ERROR: missing contract file: {CONTRACT_PATH}")
        return 2

    errors: list[str] = []
    contracts = _load_contracts()

    for contract in contracts:
        contract_id = contract.get("id") or "unknown"
        workflow_file = contract.get("workflow_file") or "_workflows/UNKNOWN"

        canonical = sorted(set(contract.get("canonical_states") or []))
        implemented = sorted(set(_extract_states(contract.get("state_source") or {})))

        undocumented = sorted(set(implemented) - set(canonical))
        missing_in_code = sorted(set(canonical) - set(implemented))

        if undocumented:
            errors.append(
                "[workflow-contracts] "
                f"{contract_id}: states are implemented but not documented in {workflow_file}: "
                + ", ".join(undocumented)
                + ". Update _workflows contract markdown and "
                + contract["state_source"]["file"]
                + " together."
            )
        if missing_in_code:
            errors.append(
                "[workflow-contracts] "
                f"{contract_id}: states documented in {workflow_file} are missing in code: "
                + ", ".join(missing_in_code)
                + ". Add model selections/constants or adjust workflow docs and contract map."
            )

        required_actions = set(contract.get("required_actions") or [])
        action_source = contract.get("action_source") or {}
        implemented_actions = _extract_actions(action_source)
        missing_actions = sorted(required_actions - implemented_actions)
        if missing_actions:
            errors.append(
                "[workflow-contracts] "
                f"{contract_id}: required actions missing in {action_source.get('file')}: "
                + ", ".join(missing_actions)
                + ". Add guarded action methods or update the contract mapping."
            )

    if errors:
        for error in errors:
            print(error)
        print(
            "[workflow-contracts] FAIL. See addons/CONTRIBUTING.md workflow contract guidance."
        )
        return 1

    print(f"[workflow-contracts] OK ({len(contracts)} contract(s) validated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
