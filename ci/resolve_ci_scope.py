#!/usr/bin/env python3
"""Resolve CI modules from changed addons and manifest reverse dependencies."""

from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def modules() -> list[str]:
    return sorted(
        path.parent.name for path in ROOT.glob("sports_federation_*/__manifest__.py")
    )


def dependencies(module: str) -> set[str]:
    manifest = ROOT / module / "__manifest__.py"
    try:
        tree = ast.parse(manifest.read_text(encoding="utf-8"))
        data = ast.literal_eval(tree.body[-1].value)
    except (OSError, SyntaxError, ValueError, AttributeError):
        return set()
    return {
        dependency for dependency in data.get("depends", []) if dependency in modules()
    }


def reverse_closure(seeds: set[str]) -> set[str]:
    reverse = {module: dependencies(module) for module in modules()}
    selected = set(seeds)
    changed = True
    while changed:
        changed = False
        for module, deps in reverse.items():
            if module not in selected and deps & selected:
                selected.add(module)
                changed = True
    return selected


def changed_modules(ref: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{ref}...HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(
            f"Cannot compare {ref!r} with HEAD: {result.stderr.strip() or 'git diff failed'}"
        )
    known = set(modules())
    return {
        path.split("/", 1)[0]
        for path in result.stdout.splitlines()
        if path.split("/", 1)[0] in known
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--affected-from")
    parser.add_argument("--include-dependents", action="store_true")
    parser.add_argument("--module", action="append", default=[])
    args = parser.parse_args()

    seeds = set(args.module)
    if args.affected_from:
        seeds |= changed_modules(args.affected_from)
    if not seeds:
        return 0
    selected = reverse_closure(seeds) if args.include_dependents else seeds
    for module in modules():
        if module in selected:
            print(module)
    return 0


if __name__ == "__main__":
    sys.exit(main())
