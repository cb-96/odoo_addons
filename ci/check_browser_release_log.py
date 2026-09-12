#!/usr/bin/env python3
"""Reject release evidence where critical browser tests were skipped or broken."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

BLOCKERS = {
    "missing websocket client": re.compile(
        r"websocket-client module is not installed", re.I
    ),
    "invalid tour registration": re.compile(
        r"web_tour\.tours.*unknown key|unknown key.*web_tour\.tours", re.I
    ),
    "tour module load failure": re.compile(
        r"modules failed to load.*sports_federation|sports_federation.*failed to load",
        re.I,
    ),
}
CRITICAL_SKIP = re.compile(
    r"skipped.*(?:sf_browser_|sports_federation_(?:demo|public_site|finance_bridge)).*browser",
    re.I,
)


def inspect(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    failures = [name for name, pattern in BLOCKERS.items() if pattern.search(text)]
    if CRITICAL_SKIP.search(text):
        failures.append("critical federation browser test skipped")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=Path)
    args = parser.parse_args()
    failures = []
    for log in args.logs:
        if not log.is_file():
            failures.append(f"{log}: missing log")
            continue
        failures.extend(f"{log}: {failure}" for failure in inspect(log))
    if failures:
        print("Browser release-log validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Browser release-log validation passed ({len(args.logs)} logs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
