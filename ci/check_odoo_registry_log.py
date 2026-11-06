#!/usr/bin/env python3
"""Reject Odoo logs that report a registry with unresolved module/model state."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REGISTRY_FAILURES = (
    (
        "inconsistent module states",
        re.compile(r"Some modules have inconsistent states"),
    ),
    (
        "unloaded modules or missing dependencies",
        re.compile(r"Some modules are not loaded, some dependencies may be missing"),
    ),
    (
        "model declared but not loadable",
        re.compile(r"Model .+ is declared but cannot be loaded!"),
    ),
)


def find_registry_failures(log_text: str) -> list[tuple[str, str]]:
    failures = []
    for line in log_text.splitlines():
        for label, pattern in REGISTRY_FAILURES:
            if pattern.search(line):
                failures.append((label, line.strip()))
                break
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", type=Path)
    args = parser.parse_args(argv)
    try:
        log_text = args.log_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"Unable to read Odoo log {args.log_file}: {exc}", file=sys.stderr)
        return 2

    failures = find_registry_failures(log_text)
    if failures:
        print("Odoo registry integrity check failed:", file=sys.stderr)
        for label, line in failures:
            print(f"- {label}: {line}", file=sys.stderr)
        return 1

    print("Odoo registry integrity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
