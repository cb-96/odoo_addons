#!/usr/bin/env python3
"""Validate the single supported federation application entry point."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = "sports_federation_app"
EXCLUDED = {APP, "sports_federation_demo"}


def manifest(module):
    path = ROOT / module / "__manifest__.py"
    return ast.literal_eval(path.read_text(encoding="utf-8"))


def main():
    modules = sorted(
        path.name
        for path in ROOT.glob("sports_federation_*")
        if path.is_dir() and (path / "__manifest__.py").exists()
    )
    failures = []
    app = manifest(APP)
    expected = set(modules) - EXCLUDED
    actual = set(app.get("depends", []))
    missing = sorted(expected - actual)
    unexpected = sorted(
        dep for dep in actual if dep.startswith("sports_federation_") and dep not in expected
    )
    if missing:
        failures.append("production addons missing from app depends: " + ", ".join(missing))
    if unexpected:
        failures.append("unexpected federation dependencies: " + ", ".join(unexpected))
    if app.get("data") or app.get("demo"):
        failures.append("application entry point must not own data or demo records")
    if not app.get("application"):
        failures.append("application entry point must set application=True")
    other_apps = [
        module for module in modules
        if module != APP and manifest(module).get("application")
    ]
    if other_apps:
        failures.append("other addons expose duplicate Apps entries: " + ", ".join(other_apps))
    forbidden = ["models", "controllers", "security", "views", "wizards", "data"]
    present = [name for name in forbidden if (ROOT / APP / name).exists()]
    if present:
        failures.append("entry point contains business implementation directories: " + ", ".join(present))
    if failures:
        print("Application entry-point validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Application entry-point validation passed ({len(expected)} production addons).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
