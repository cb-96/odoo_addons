#!/usr/bin/env python3
"""Verify that every Odoo test module is imported exactly once."""

from __future__ import annotations
import ast
from pathlib import Path
import re
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
runner_path = ROOT / "ci" / "run_tests.sh"
runner_source = runner_path.read_text(encoding="utf-8")
module_registry = re.search(
    r"^ALL_MODULES=\(\s*(.*?)^\)", runner_source, re.MULTILINE | re.DOTALL
)
if not module_registry:
    errors.append("ci/run_tests.sh: cannot find the ALL_MODULES registry")
else:
    configured_modules = re.findall(
        r"^\s*(sports_federation_[a-z0-9_]+)\s*$",
        module_registry.group(1),
        re.MULTILINE,
    )
    manifest_modules = {
        path.parent.name for path in ROOT.glob("sports_federation_*/__manifest__.py")
    }
    missing_modules = sorted(manifest_modules - set(configured_modules))
    unknown_modules = sorted(set(configured_modules) - manifest_modules)
    duplicates = sorted(
        {module for module in configured_modules if configured_modules.count(module) > 1}
    )
    if missing_modules:
        errors.append(
            "ci/run_tests.sh: installable addon modules missing from ALL_MODULES: "
            + ", ".join(missing_modules)
        )
    if unknown_modules:
        errors.append(
            "ci/run_tests.sh: unknown modules in ALL_MODULES: "
            + ", ".join(unknown_modules)
        )
    if duplicates:
        errors.append(
            "ci/run_tests.sh: duplicate modules in ALL_MODULES: "
            + ", ".join(duplicates)
        )

if not re.search(r"^REQUIRE_POST_TESTS=1$", runner_source, re.MULTILINE):
    errors.append("ci/run_tests.sh: CI runs must require at least one post-test by default")
if '--addons-path="$ADDONS_PATH"' not in runner_source:
    errors.append("ci/run_tests.sh: Odoo must receive the explicit custom addons path")
if 'odoo --addons-path="$ADDONS_PATH" server --config=/etc/odoo/odoo.conf' not in runner_source:
    errors.append("ci/run_tests.sh: Odoo server options must follow the Odoo 19 server subcommand")
if ' --stop-after-init "\\$@"' not in runner_source:
    errors.append("ci/run_tests.sh: generated Odoo shell must forward install/test arguments")
if r'run_odoo "\${DEMO_ARGS[@]}"' not in runner_source:
    errors.append("ci/run_tests.sh: generated Odoo shell must preserve optional demo arguments")
if "--entrypoint bash" not in runner_source:
    errors.append("ci/run_tests.sh: CI shell script must override the Odoo image entrypoint")
required_install_phases = (
    r'run_odoo "\${DEMO_ARGS[@]}" -d "$CI_ODOO_DB_NAME" -i "$MODULE_CSV"',
    r'run_odoo "\${DEMO_ARGS[@]}" --test-enable --test-tags="$TEST_TAGS" '
    '-d "$CI_ODOO_DB_NAME" -u "$MODULE_CSV"',
)
for phase in required_install_phases:
    if phase not in runner_source:
        errors.append(
            "ci/run_tests.sh: install all addons before running the test-enabled upgrade"
        )

if errors:
    print("Odoo test discovery contract failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(1)
print("Odoo test discovery contract passed.")
