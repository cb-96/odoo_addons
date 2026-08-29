#!/usr/bin/env python3
"""Validate manifests, explicit assets, Python imports and model ACL coverage."""

from __future__ import annotations
import ast
import csv
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
addons = sorted(path.parent for path in ROOT.glob("*/__manifest__.py"))


def manifest_for(addon: Path) -> dict:
    try:
        value = ast.literal_eval(
            (addon / "__manifest__.py").read_text(encoding="utf-8")
        )
    except (OSError, SyntaxError, ValueError) as exc:
        errors.append(f"{addon.name}: manifest cannot be parsed: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{addon.name}: manifest is not a dictionary")
        return {}
    return value


def concrete_models(addon: Path) -> set[str]:
    result = set()
    for path in addon.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: cannot parse: {exc}")
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {
                base.attr if isinstance(base, ast.Attribute) else base.id
                for base in node.bases
                if isinstance(base, (ast.Attribute, ast.Name))
            }
            if "AbstractModel" in base_names or "TransientModel" in base_names:
                continue
            model = None
            inherited = False
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                names = {
                    target.id
                    for target in statement.targets
                    if isinstance(target, ast.Name)
                }
                if "_inherit" in names:
                    inherited = True
                if (
                    "_name" in names
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                ):
                    model = statement.value.value
            # Extensions of an existing model obtain ACLs from the owning addon.
            if model and not inherited:
                result.add(model)
    return result


def acl_models(addon: Path) -> set[str]:
    path = addon / "security" / "ir.model.access.csv"
    if not path.is_file():
        return set()
    result = set()
    with path.open(encoding="utf-8", newline="") as stream:
        # Ignore harmless leading blank lines so DictReader sees the real header.
        rows = (line for line in stream if line.strip())
        for row in csv.DictReader(rows):
            external_id = row.get("model_id:id", "")
            if external_id.startswith("model_"):
                result.add(external_id)
    return result


available = {addon.name for addon in addons}
for addon in addons:
    manifest = manifest_for(addon)
    for dependency in manifest.get("depends", []):
        if (
            isinstance(dependency, str)
            and dependency.startswith("sports_federation_")
            and dependency not in available
        ):
            errors.append(f"{addon.name}: unresolved internal dependency {dependency}")
    for value in manifest.get("data", []):
        if not isinstance(value, str) or not (addon / value).is_file():
            errors.append(f"{addon.name}: missing manifest data file {value!r}")
    for entries in manifest.get("assets", {}).values():
        if not isinstance(entries, (list, tuple)):
            continue
        for entry in entries:
            if (
                not isinstance(entry, str)
                or not entry.startswith(addon.name + "/")
                or any(char in entry for char in "*?[")
            ):
                continue
            if not (ROOT / entry).is_file():
                errors.append(f"{addon.name}: missing explicit asset {entry}")
    for init in addon.rglob("__init__.py"):
        for line_number, line in enumerate(
            init.read_text(encoding="utf-8").splitlines(), 1
        ):
            match = re.match(r"\s*from\s+\.\s+import\s+([A-Za-z0-9_, ]+)", line)
            if not match:
                continue
            for name in (item.strip() for item in match.group(1).split(",")):
                if name and not (
                    (init.parent / f"{name}.py").is_file()
                    or (init.parent / name / "__init__.py").is_file()
                ):
                    errors.append(
                        f"{init.relative_to(ROOT)}:{line_number}: missing imported module {name}"
                    )
    declared_acl = acl_models(addon)
    missing_acl = {
        model
        for model in concrete_models(addon)
        if "model_" + model.replace(".", "_") not in declared_acl
    }
    if missing_acl:
        errors.append(
            f"{addon.name}: concrete models without ACL: {', '.join(sorted(missing_acl))}"
        )
if errors:
    print("Addon integrity check failed:")
    for error in sorted(set(errors)):
        print(f"- {error}")
    sys.exit(1)
print(f"Addon integrity check passed for {len(addons)} addons.")
