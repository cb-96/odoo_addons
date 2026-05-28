#!/usr/bin/env python3
"""Validate committed EXPLAIN snapshots for the largest reporting SQL views."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = REPO_ROOT / "ci" / "explain_snapshots"
EXPECTED_SNAPSHOTS = {
    "federation_report_season_portfolio.txt": (
        "WindowAgg",
        "Sort",
        "HashAggregate",
        "GroupAggregate",
    ),
    "federation_report_club_performance.txt": (
        "WindowAgg",
        "Sort",
        "HashAggregate",
        "GroupAggregate",
    ),
}
REQUIRED_HEADERS = (
    "# Captured at:",
    "# Database:",
    "# Season ID:",
    "# Query:",
)


def main() -> int:
    failures: list[str] = []
    for filename, operators in EXPECTED_SNAPSHOTS.items():
        path = SNAPSHOT_DIR / filename
        if not path.exists():
            failures.append(f"Missing EXPLAIN snapshot: {path.relative_to(REPO_ROOT)}")
            continue

        content = path.read_text(encoding="utf-8")
        for header in REQUIRED_HEADERS:
            if header not in content:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)} is missing header '{header}'"
                )
        if not any(operator in content for operator in operators):
            failures.append(
                f"{path.relative_to(REPO_ROOT)} does not contain any expected heavy-plan operators: {', '.join(operators)}"
            )

    if failures:
        print("EXPLAIN snapshot validation failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("EXPLAIN snapshot validation passed for committed reporting plans.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
