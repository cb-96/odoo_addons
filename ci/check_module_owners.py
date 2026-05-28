#!/usr/bin/env python3
"""Validate the per-module ownership registry against installed addons."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "MODULE_OWNERS.yaml"
MODULE_GLOB = "sports_federation_*/__manifest__.py"
REQUIRED_TOP_LEVEL_FIELDS = ("owner", "last_reviewed", "review_cadence")
REQUIRED_MODULE_FIELDS = ("primary_owner", "secondary_owner", "surface")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _load_registry() -> dict:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("MODULE_OWNERS.yaml must contain a top-level mapping.")
    return loaded


def _discover_modules() -> list[str]:
    return sorted(path.parent.name for path in REPO_ROOT.glob(MODULE_GLOB))


def main() -> int:
    failures: list[str] = []
    _expect(
        REGISTRY_PATH.exists(),
        f"Missing module owner registry: {REGISTRY_PATH.relative_to(REPO_ROOT)}",
        failures,
    )
    if failures:
        print("\n".join(failures))
        return 1

    try:
        registry = _load_registry()
    except Exception as error:  # pragma: no cover - exercised through CLI use
        print(f"Unable to parse {REGISTRY_PATH.relative_to(REPO_ROOT)}: {error}")
        return 1

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        value = registry.get(field)
        _expect(
            bool(str(value or "").strip()),
            f"MODULE_OWNERS.yaml requires top-level '{field}'.",
            failures,
        )

    last_reviewed = str(registry.get("last_reviewed", "")).strip()
    if last_reviewed:
        _expect(
            bool(DATE_PATTERN.match(last_reviewed)),
            "MODULE_OWNERS.yaml last_reviewed must use YYYY-MM-DD.",
            failures,
        )

    modules = registry.get("modules")
    _expect(
        isinstance(modules, dict),
        "MODULE_OWNERS.yaml requires a top-level 'modules' mapping.",
        failures,
    )
    if not isinstance(modules, dict):
        print("Module owner registry validation failed:\n")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1

    discovered_modules = set(_discover_modules())
    registered_modules = set(modules)
    missing_modules = sorted(discovered_modules - registered_modules)
    extra_modules = sorted(registered_modules - discovered_modules)
    _expect(
        not missing_modules,
        f"Modules missing from owner registry: {', '.join(missing_modules)}",
        failures,
    )
    _expect(
        not extra_modules,
        f"Unknown modules listed in owner registry: {', '.join(extra_modules)}",
        failures,
    )

    for module_name in sorted(registered_modules):
        metadata = modules.get(module_name)
        _expect(
            isinstance(metadata, dict),
            f"{module_name}: owner entry must be a mapping.",
            failures,
        )
        if not isinstance(metadata, dict):
            continue
        for field in REQUIRED_MODULE_FIELDS:
            value = metadata.get(field)
            _expect(
                isinstance(value, str) and bool(value.strip()),
                f"{module_name}: missing '{field}'.",
                failures,
            )

    if failures:
        print("Module owner registry validation failed:\n")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1

    print(
        "Module owner registry validation passed for "
        f"{REGISTRY_PATH.relative_to(REPO_ROOT)} ({len(discovered_modules)} modules)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
