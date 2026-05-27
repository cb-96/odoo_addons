#!/usr/bin/env python3
"""Report cross-addon import drift against manifest depends.

This check is intentionally non-blocking by default.
Use --strict to make missing dependency imports fail with exit code 1.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE_PREFIX = "sports_federation_"
IMPORT_RE = re.compile(r"odoo\.addons\.(sports_federation_[a-z0-9_]+)")


def _module_dirs() -> list[pathlib.Path]:
    return sorted(
        path
        for path in ROOT.iterdir()
        if path.is_dir() and path.name.startswith(MODULE_PREFIX)
    )


def _manifest_depends(module_dir: pathlib.Path) -> set[str]:
    manifest_path = module_dir / "__manifest__.py"
    if not manifest_path.exists():
        return set()
    try:
        manifest_obj = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    depends = manifest_obj.get("depends", []) if isinstance(manifest_obj, dict) else []
    if not isinstance(depends, list):
        return set()
    return {dep for dep in depends if isinstance(dep, str)}


def _import_targets(module_dir: pathlib.Path) -> set[str]:
    targets: set[str] = set()
    for py_file in module_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for match in IMPORT_RE.findall(content):
            targets.add(match)
    return targets


def run(strict: bool) -> int:
    module_dirs = _module_dirs()
    violations: list[str] = []

    for module_dir in module_dirs:
        module_name = module_dir.name
        depends = _manifest_depends(module_dir)
        imported_addons = _import_targets(module_dir)

        for imported in sorted(imported_addons):
            if imported == module_name:
                continue
            if imported not in depends:
                violations.append(
                    f"{module_name}: imports {imported} but it is missing from __manifest__.py depends"
                )

    if violations:
        for violation in violations:
            print(f"[dependency-drift] WARN: {violation}")
        if strict:
            return 1

    print(f"[dependency-drift] Checked {len(module_dirs)} modules")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check addon import drift against manifest depends"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Return non-zero when drift is found"
    )
    args = parser.parse_args()
    return run(strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
