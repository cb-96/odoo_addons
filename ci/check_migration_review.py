#!/usr/bin/env python3
"""Fail when upgrade-sensitive changes land without migration review evidence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GLOBAL_REVIEW_FILES = {
    "TECHNICAL_NOTE.md",
    "RELEASE_RUNBOOK.md",
    "RELEASE_TRAIN.md",
}
ROUTE_REVIEW_FILES = {
    "ROUTE_INVENTORY.md",
    "STATE_AND_OWNERSHIP_MATRIX.md",
}
SENSITIVE_SURFACES = {
    "models": "model ownership",
    "views": "view ownership",
    "controllers": "route ownership",
}


def _normalize_repo_path(path_text: str) -> str:
    path = path_text.strip().replace("\\", "/")
    if not path:
        return ""
    if path.startswith("addons/"):
        path = path[len("addons/") :]
    return path.lstrip("./")


def _changed_files_from_git(base_ref: str | None, head_ref: str) -> list[str]:
    if base_ref:
        diff_target = f"{base_ref}...{head_ref}"
    else:
        parent = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if parent.returncode != 0:
            return []
        diff_target = f"HEAD^...{head_ref}"

    result = subprocess.run(
        ["git", "diff", "--name-only", diff_target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            result.stderr.strip() or "Unable to resolve changed files from git."
        )
    return [
        _normalize_repo_path(line)
        for line in result.stdout.splitlines()
        if _normalize_repo_path(line)
    ]


def _find_sensitive_changes(changed_files: list[str]) -> dict[str, set[str]]:
    sensitive = defaultdict(set)
    for path in changed_files:
        parts = path.split("/")
        if len(parts) < 3:
            continue
        module_name, surface = parts[0], parts[1]
        if module_name.startswith(".") or surface not in SENSITIVE_SURFACES:
            continue
        sensitive[module_name].add(surface)
    return sensitive


def _has_review_evidence(
    module_name: str, surfaces: set[str], changed_files: set[str]
) -> bool:
    if changed_files & GLOBAL_REVIEW_FILES:
        return True
    if f"{module_name}/README.md" in changed_files:
        return True
    if any(path.startswith(f"{module_name}/migrations/") for path in changed_files):
        return True
    if "controllers" in surfaces and changed_files & ROUTE_REVIEW_FILES:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Explicit git base ref for diff collection.")
    parser.add_argument(
        "--head-ref", default="HEAD", help="Git head ref for diff collection."
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="Explicit changed files relative to the repo root. When set, git diff is skipped.",
    )
    args = parser.parse_args()

    changed_files = [
        _normalize_repo_path(path)
        for path in (args.files or [])
        if _normalize_repo_path(path)
    ]
    if not changed_files:
        changed_files = _changed_files_from_git(args.base_ref, args.head_ref)
    if not changed_files:
        print("No changed files detected; skipping migration review check.")
        return 0

    changed_file_set = set(changed_files)
    sensitive_changes = _find_sensitive_changes(changed_files)
    failures = []
    for module_name, surfaces in sorted(sensitive_changes.items()):
        if _has_review_evidence(module_name, surfaces, changed_file_set):
            continue
        surface_labels = ", ".join(
            SENSITIVE_SURFACES[surface] for surface in sorted(surfaces)
        )
        failures.append(
            f"- {module_name}: changed {surface_labels} without touching a migration script, module README, "
            "TECHNICAL_NOTE.md, RELEASE_RUNBOOK.md, RELEASE_TRAIN.md, or the route inventory docs."
        )

    if failures:
        print("Migration review is required for upgrade-sensitive changes:\n")
        print("\n".join(failures))
        return 1

    print("Migration review evidence found for all upgrade-sensitive changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
