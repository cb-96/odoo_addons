#!/usr/bin/env python3
"""Require a local rationale for always-invisible fields in Odoo views."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

FIELD = re.compile(r'<field\b[^>]*\bname=["\']([^"\']+)["\'][^>]*>')
INVISIBLE = re.compile(r'\binvisible=["\'](?:1|True|true)["\']')
COMMENT = re.compile(r'<!--\s*(.*?)\s*-->', re.DOTALL)
RATIONALE = ("modifier", "domain", "context", "decoration", "technical", "relay")


def violations(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    failures: list[str] = []
    for index, line in enumerate(lines):
        match = FIELD.search(line)
        if not match or not INVISIBLE.search(line):
            continue
        nearby = "\n".join(lines[max(0, index - 2) : index])
        comments = " ".join(COMMENT.findall(nearby)).lower()
        if not any(word in comments for word in RATIONALE):
            failures.append(f"{path}:{index + 1}: {match.group(1)}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.paths or sorted(Path(".").glob("sports_federation_*/views/**/*.xml"))
    failures = [failure for path in paths for failure in violations(path)]
    if failures:
        print("Always-invisible view fields need an adjacent rationale comment:")
        for failure in failures:
            print(f"- {failure}")
        print("Use a short comment explaining the modifier, domain, context, decoration, or technical relay.")
        return 1
    print(f"Always-invisible view field check passed ({len(paths)} XML files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
