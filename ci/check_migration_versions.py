#!/usr/bin/env python3
"""Fail when an addon manifest is older than one of its own migrations.

Odoo runs a migration folder ``19.0.X.Y.Z`` when a database upgrades from a
version below it to a manifest version at or above it. A manifest that is
*behind* its newest migration (typically after a merge that reverted the
version) breaks that contract:

- migrations numbered between the manifest and the newest folder never run on
  databases that already passed the newest folder, and
- the version recorded in the database moves backwards on upgrade.

Also checks that migration folder names are well formed and that every
migration folder holds at least one script.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^\d+\.\d+(?:\.\d+){1,3}$")


def version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def check(root: Path) -> list[str]:
    errors = []
    for manifest_path in sorted(root.glob("*/__manifest__.py")):
        addon = manifest_path.parent
        manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
        version = manifest.get("version", "")
        if not VERSION.match(version):
            errors.append(f"{addon.name}: manifest version {version!r} is malformed")
            continue
        migrations = addon / "migrations"
        if not migrations.is_dir():
            continue
        newest = None
        for folder in sorted(migrations.iterdir()):
            if not folder.is_dir() or folder.name == "__pycache__":
                continue
            if not VERSION.match(folder.name):
                errors.append(
                    f"{addon.name}/migrations/{folder.name}: not a version folder"
                )
                continue
            if not any(folder.glob("*.py")):
                errors.append(f"{addon.name}/migrations/{folder.name}: no script")
            if newest is None or version_key(folder.name) > version_key(newest):
                newest = folder.name
        if newest and version_key(newest) > version_key(version):
            errors.append(
                f"{addon.name}: manifest version {version} is older than its newest "
                f"migration {newest}; raise the manifest version"
            )
    return errors


def main() -> int:
    errors = check(ROOT)
    if errors:
        print("Migration version check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Migration version check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
