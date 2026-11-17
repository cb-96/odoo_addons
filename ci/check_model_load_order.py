#!/usr/bin/env python3
"""Check that every model extension can be built when Odoo loads its addon.

Odoo builds the models of an addon in import order. A class that extends a
model (``_inherit``) fails the registry load with ``TypeError: Model ... does
not exist in registry`` when:

- the base model is defined later in the same addon, or
- the base model belongs to a repository addon that is not a dependency.

Models that no repository addon defines come from Odoo itself and are skipped.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifests(root: Path) -> dict[str, dict]:
    result = {}
    for path in sorted(root.glob("*/__manifest__.py")):
        result[path.parent.name] = ast.literal_eval(path.read_text(encoding="utf-8"))
    return result


def dependency_closure(addon: str, addons: dict[str, dict]) -> set[str]:
    seen: set[str] = set()
    pending = list(addons.get(addon, {}).get("depends", []))
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(addons.get(name, {}).get("depends", []))
    return seen


def import_order(package: Path) -> list[Path]:
    """Python files in the order the package ``__init__`` chain imports them."""
    order: list[Path] = []

    def visit(init: Path) -> None:
        tree = ast.parse(init.read_text(encoding="utf-8"), filename=str(init))
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or node.level != 1:
                continue
            if node.module:
                targets = [init.parent / node.module.replace(".", "/")]
            else:
                targets = [init.parent / alias.name for alias in node.names]
            for target in targets:
                if (target / "__init__.py").is_file():
                    visit(target / "__init__.py")
                elif target.with_suffix(".py").is_file():
                    order.append(target.with_suffix(".py"))

    if (package / "__init__.py").is_file():
        visit(package / "__init__.py")
    return order


def _strings(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            item.value
            for item in node.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        ]
    return []


def model_classes(path: Path) -> list[tuple[int, str, str | None, list[str]]]:
    """(line, class name, _name, _inherit list) for every class in a file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name, inherit = None, []
        for statement in node.body:
            if not (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                continue
            key = statement.targets[0].id
            if key == "_name":
                name = (_strings(statement.value) or [None])[0]
            elif key == "_inherit":
                inherit = _strings(statement.value)
        if name or inherit:
            result.append((node.lineno, node.name, name, inherit))
    return result


def check(root: Path) -> list[str]:
    addons = manifests(root)
    classes = {
        addon: [
            (path, *row)
            for path in import_order(root / addon)
            if "tests" not in path.relative_to(root / addon).parts
            for row in model_classes(path)
        ]
        for addon in addons
    }
    owner: dict[str, str] = {}
    for addon, rows in classes.items():
        for _path, _line, _cls, name, inherit in rows:
            if name and name not in inherit:
                owner.setdefault(name, addon)

    errors = []
    for addon, rows in classes.items():
        dependencies = dependency_closure(addon, addons)
        built: set[str] = set()
        for path, line, cls, name, inherit in rows:
            where = f"{path.relative_to(root).as_posix()}:{line} {cls}"
            for parent in inherit:
                base_addon = owner.get(parent)
                if base_addon is None:
                    continue
                if base_addon == addon and parent not in built:
                    errors.append(
                        f"{where} extends {parent} before {addon} defines it; "
                        "import the defining module first"
                    )
                elif base_addon != addon and base_addon not in dependencies:
                    errors.append(
                        f"{where} extends {parent} from {base_addon}, "
                        f"which {addon} does not depend on"
                    )
            if name:
                built.add(name)
    return errors


def main() -> int:
    errors = check(ROOT)
    if errors:
        print("Model load order check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Model load order check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
