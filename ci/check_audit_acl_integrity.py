#!/usr/bin/env python3
"""Ensure ordinary access groups cannot delete immutable audit evidence."""

from __future__ import annotations

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_MODELS = {
    "model_federation_audit_event",
    "model_federation_match_result_audit",
    "model_federation_participation_audit",
}


def find_violations(root: Path = ROOT) -> list[str]:
    violations = []
    paths = root.glob("sports_federation_*/security/ir.model.access.csv")
    for path in sorted(paths):
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("model_id:id") not in PROTECTED_MODELS:
                    continue
                if row.get("perm_unlink") == "1":
                    violations.append(
                        f"{path.relative_to(root).as_posix()}: {row.get('id')} "
                        "grants unlink on immutable audit evidence"
                    )
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Audit ACL integrity check failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Audit ACL integrity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
