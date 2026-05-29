#!/usr/bin/env python3
"""Validate CI layout and log retention hygiene."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

CI_DIR = pathlib.Path(__file__).resolve().parent
LEGACY_COMPOSE_DIR = CI_DIR / "legacy" / "compose"
ACTIVE_COMPOSE = {"docker-compose.ci.yaml"}
KNOWN_LEGACY_COMPOSE = {
    "docker-compose.override.yaml",
    "docker-compose.phase3_officiating.yaml",
    "docker-compose.public_site.phase2.yaml",
    "docker-compose.result_control.phase2.yaml",
    "docker-compose.rosters.phase2.yaml",
    "docker-compose.sf_engine.yaml",
    "docker-compose.temp.yaml",
    "docker-compose.temp_task.yaml",
}

MAX_LOG_FILES = int(os.getenv("CI_MAX_LOG_FILES", "1500"))
MAX_LOG_BYTES = int(os.getenv("CI_MAX_LOG_BYTES", str(100 * 1024 * 1024)))


def _list_compose_files(path: pathlib.Path) -> set[str]:
    if not path.exists():
        return set()
    return {p.name for p in path.glob("docker-compose*.yaml") if p.is_file()}


def _logs_metrics(logs_dir: pathlib.Path) -> tuple[int, int]:
    if not logs_dir.exists():
        return 0, 0
    total_files = 0
    total_bytes = 0
    for file_path in logs_dir.rglob("*"):
        if file_path.is_file():
            total_files += 1
            total_bytes += file_path.stat().st_size
    return total_files, total_bytes


def _tracked_bytecode_artifacts(repo_root: pathlib.Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        # Do not fail hygiene if git metadata is unavailable in the environment.
        return []

    tracked = []
    for rel_path in result.stdout.splitlines():
        if rel_path.endswith(".pyc") or "/__pycache__/" in rel_path:
            tracked.append(rel_path)
    return tracked


def main() -> int:
    errors: list[str] = []
    repo_root = CI_DIR.parent

    root_compose = _list_compose_files(CI_DIR)
    unexpected_root = sorted(root_compose - ACTIVE_COMPOSE)
    if unexpected_root:
        errors.append(
            "Unexpected compose files in ci/ root (move to ci/legacy/compose): "
            + ", ".join(unexpected_root)
        )

    legacy_compose = _list_compose_files(LEGACY_COMPOSE_DIR)
    unknown_legacy = sorted(legacy_compose - KNOWN_LEGACY_COMPOSE)
    if unknown_legacy:
        errors.append(
            "Unknown compose files in ci/legacy/compose: " + ", ".join(unknown_legacy)
        )

    logs_files, logs_bytes = _logs_metrics(CI_DIR / "logs")
    if logs_files > MAX_LOG_FILES:
        errors.append(
            f"ci/logs has {logs_files} files (limit {MAX_LOG_FILES}). "
            "Run ci/prune_ci_logs.sh or lower retention."
        )
    if logs_bytes > MAX_LOG_BYTES:
        errors.append(
            f"ci/logs size is {logs_bytes} bytes (limit {MAX_LOG_BYTES}). "
            "Run ci/prune_ci_logs.sh or lower retention."
        )

    tracked_bytecode = _tracked_bytecode_artifacts(repo_root)
    if tracked_bytecode:
        errors.append(
            "Tracked Python bytecode artifacts detected: "
            + ", ".join(sorted(tracked_bytecode)[:10])
            + (
                f" (and {len(tracked_bytecode) - 10} more)"
                if len(tracked_bytecode) > 10
                else ""
            )
            + ". Remove them with: git rm --cached <paths>."
        )

    if errors:
        for err in errors:
            print(f"[ci-hygiene] ERROR: {err}")
        return 1

    print("[ci-hygiene] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
