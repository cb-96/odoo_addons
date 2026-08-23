#!/usr/bin/env python3
"""Static contract for complete source-bundle discovery."""

from pathlib import Path
import ast
import sys

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "source_collector.py"
errors = []
if not COLLECTOR.is_file():
    errors.append("source_collector.py is missing")
else:
    text = COLLECTOR.read_text(encoding="utf-8")
    try:
        ast.parse(text, filename=str(COLLECTOR))
    except SyntaxError as exc:
        errors.append(f"collector syntax error: {exc}")
    required_tokens = {
        '".sh"': "shell extension support",
        '".bash"': "bash extension support",
        "discover_addons()": "dynamic addon discovery",
        "validate_internal_dependencies": "internal dependency validation",
        'Path("ci/logs")': "generated CI log exclusion",
        "collect_repository_root_files": "root document discovery",
    }
    for token, purpose in required_tokens.items():
        if token not in text:
            errors.append(f"collector lacks {purpose}: {token}")
for item in (
    "ci/run_tests.sh",
    "ci/run_odoo_tests.sh",
    "scripts/ci/run_rc_validation.sh",
):
    if not (ROOT / item).is_file():
        errors.append(f"required review source is missing: {item}")
if errors:
    print("Source collector contract failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)
print("Source collector contract passed.")
