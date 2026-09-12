#!/usr/bin/env python3
"""Reject vague or incomplete privileged-call justifications."""
import json
from pathlib import Path
import sys

INVENTORY = Path("docs/portal_sudo_inventory.json")
VAGUE = {"", "sudo required", "needed", "temporary", "legacy"}


def violations(path=INVENTORY):
    entries = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    for index, entry in enumerate(entries):
        missing = {"file", "function", "statement", "reason"} - set(entry)
        if missing:
            failures.append(f"entry {index} missing {', '.join(sorted(missing))}")
            continue
        reason = entry["reason"].strip().lower()
        if reason in VAGUE or len(reason) < 12:
            failures.append(f"{entry['file']}:{entry['function']} has a vague reason")
        if ".sudo()" not in entry["statement"]:
            failures.append(f"{entry['file']}:{entry['function']} has no sudo statement")
    return failures


def main():
    failures = violations()
    if failures:
        print("Privileged inventory quality check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Privileged inventory quality check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
