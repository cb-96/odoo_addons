#!/usr/bin/env python3
"""Validate shared release-train metadata across top-level release surfaces."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRAIN_FILES = [
    "RELEASE_TRAIN.md",
    "ROADMAP.md",
    "RELEASE_RUNBOOK.md",
]
TRAIN_PATTERN = re.compile(r"^\d{4}\.\d{2}$")


def _read_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines()[:12]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def main() -> int:
    failures: list[str] = []
    train_values: dict[str, str] = {}

    for rel_path in TRAIN_FILES:
        path = REPO_ROOT / rel_path
        if not path.exists():
            failures.append(f"{rel_path}: file is missing")
            continue

        metadata = _read_metadata(path)
        train_value = metadata.get("Release train", "")
        if not train_value:
            failures.append(
                f"{rel_path}: missing 'Release train:' metadata near the top of the file"
            )
            continue
        if not TRAIN_PATTERN.match(train_value):
            failures.append(
                f"{rel_path}: release train must use YYYY.MM, found '{train_value}'"
            )
            continue
        train_values[rel_path] = train_value

    unique_trains = sorted(set(train_values.values()))
    if len(unique_trains) > 1:
        failures.append(
            "Release train metadata must match across release surfaces: "
            + ", ".join(
                f"{path}={train}" for path, train in sorted(train_values.items())
            )
        )

    if failures:
        print("Release train metadata check failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    active_train = unique_trains[0] if unique_trains else "unknown"
    print(f"Release train metadata is aligned across release surfaces: {active_train}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
